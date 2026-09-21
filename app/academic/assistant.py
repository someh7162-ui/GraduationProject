"""Durable, bounded orchestration. Trusted state always overrides model claims."""
import copy
import re
from sqlalchemy import text
from app.access import profile_identity
from . import store, llm
from .rules import calculate, evaluate, verify
from .schemas import Fact

DESCRIPTIONS = {
    'find_policy': '查找学校、奖学金、评选年度与考核学年匹配的已确认政策',
    'read_profile': '读取当前登录用户已确认的学业档案',
    'calculate_metrics': '按政策课程口径调用确定性指标计算',
    'check_conditions': '加载全部政策规则，逐项核验包含例外分支',
    'request_information': '保存缺失字段并暂停评估，等待用户补充',
    'prepare_guidance': '依据政策条款整理材料清单和办理步骤',
    'review_assessment': '核查证据与数值，复核初评报告',
}

LABELS = {
    'transcript_complete': '确认该考核学年的课程已全部导入',
    'academic_rank': '学习成绩排名',
    'comprehensive_rank': '综合测评排名',
    'courses': '导入该学年成绩',
    'course_credits': '补全课程学分',
    'physical_education': '补充政策要求学年的体育课程成绩',
    'grade_level': '确认当前年级',
    'has_active_discipline': '确认是否存在未解除的违纪处分',
}


def questions(missing, policy, metrics=None):
    all_rules = policy['common_rules'] + [r for b in policy['branches'] for r in b['rules']]
    result = []
    for field in missing:
        rule = next((r for r in all_rules if r['field'] in (field, field + '_ratio')), None)
        kind = 'rank' if field.endswith('_rank') else 'boolean' if field == 'transcript_complete' or rule and isinstance(rule['value'], bool) else 'number' if field in ('physical_education', 'grade_level') or rule and type(rule['value']) in (int, float) else 'text'
        result.append({'field': field, 'label': LABELS.get(field, rule['label'] if rule else field), 'kind': kind,
                       'scope': rule.get('scope') if rule else None,
                       'academic_year': metrics.get('pe_policy_academic_year') if field == 'physical_education' and metrics else policy['academic_year'],
                       'help': '请提供名次、总人数、排名范围；排名类型必须与本项一致。' if kind == 'rank' else '请按实际材料填写，未知可暂不填写。'})
    return result


def run(engine, session_id, user_id):
    def checkpoint(payload, status='running'):
        with engine.begin() as conn:
            current = store.get(conn, store.sessions, session_id, user_id)
            store.save(conn, store.sessions, current, payload, status)

    with engine.connect() as conn:
        session = store.get(conn, store.sessions, session_id, user_id)
    payload = copy.deepcopy(session['payload'])
    previous_pending = payload.get('pending', [])
    payload.setdefault('runs', []).append({'tools': payload.get('tools', []), 'status': session['status'], 'at': store.now()})
    payload.update(pending=[], suggested_facts={}, error=None, tools=[], mode='model-tools' if llm.enabled() else 'local-tools')
    context = payload['context']
    if not context.get('selection_year') or not context.get('academic_year'):
        payload['messages'].append({'role': 'assistant', 'text': '请明确评选年度与考核学年。评选年度和成绩所属学年可能不同。'})
        payload['pending'] = [{'field': 'selection_year', 'label': '评选年度', 'kind': 'context'}, {'field': 'academic_year', 'label': '考核学年', 'kind': 'context'}]
        checkpoint(payload, 'waiting')
        return
    completed, policy, snapshot, report, review_log = set(), None, None, None, []
    try:
        last_message = payload['messages'][-1]
        if previous_pending and llm.enabled() and last_message.get('text') and not last_message.get('facts_submitted'):
            answer = llm.call_structured('suggest_facts', '仅从用户回复提取待补充事实，不能用政策要求替用户填写。排名必须明确 rank、total、scope、type；缺失项保留空值。返回字典，每个值符合 Fact schema。',
                {'facts_json': {'type': 'string'}}, ['facts_json'], {'reply': last_message['text'], 'pending': previous_pending, 'schema': Fact.model_json_schema()})
            import json
            suggestions = json.loads(answer['facts_json'])
            allowed = {q['field'] for q in previous_pending if q['kind'] != 'context'}
            if not isinstance(suggestions, dict) or set(suggestions) - allowed:
                raise ValueError('提取的补充信息不符合待补充字段，请用表单确认')
            if suggestions:
                payload['suggested_facts'] = {k: Fact.model_validate(v).model_dump() for k,v in suggestions.items()}
                payload['pending'] = previous_pending
                payload['messages'].append({'role': 'assistant', 'text': '已从回复提取补充信息，请核对下方表单并确认，确认后继续评估。'})
                checkpoint(payload, 'waiting')
                return
        for step in range(12):
            if not {'find_policy', 'read_profile'} <= completed:
                available = [n for n in ('find_policy', 'read_profile') if n not in completed]
            elif 'calculate_metrics' not in completed:
                available = ['calculate_metrics']
            elif 'check_conditions' not in completed:
                available = ['check_conditions']
            elif report['missing'] and report['status'] != 'fail':
                available = ['request_information']
            else:
                available = [name for name in ('prepare_guidance', 'review_assessment') if name not in completed]
            tool = llm.choose_tool({n: DESCRIPTIONS[n] for n in available}, {'context': context, 'completed': sorted(completed), 'question': payload['messages'][-1]['text'], 'missing': report['missing'] if report else []}) if llm.enabled() else available[0]
            event = {'name': tool, 'summary': DESCRIPTIONS[tool], 'at': store.now(), 'status': 'running'}
            payload['tools'].append(event)
            checkpoint(payload)
            if tool == 'find_policy':
                with engine.connect() as conn:
                    candidates = [p for p in store.listing(conn, store.policies) if p['status'] == 'active' and all(p['payload'].get(k) == context[k] for k in ('school', 'scholarship', 'selection_year', 'academic_year'))]
                if len(candidates) != 1:
                    event['status'] = 'blocked'
                    payload['messages'].append({'role': 'assistant', 'text': '未找到唯一适用的已确认政策，请管理员导入并确认对应年度通知、评审办法和附件。不能用其他年度或普通校园新闻替代。'})
                    checkpoint(payload, 'policy_missing')
                    return
                policy_record = candidates[0]
                policy = policy_record['payload']
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity
                clauses = policy['clauses']
                try:
                    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2,4))
                    matrix = vectorizer.fit_transform([c['text'] for c in clauses])
                    scores = cosine_similarity(vectorizer.transform([payload['messages'][-1]['text']]), matrix)[0]
                    order = sorted(range(len(clauses)), key=lambda i: scores[i], reverse=True)[:5]
                    payload['retrieved_clauses'] = [dict(clauses[i], similarity=float(scores[i])) for i in order]
                except ValueError:
                    payload['retrieved_clauses'] = clauses[:5]
                year = str(context['selection_year'])
                if (policy.get('effective_from') and year < policy['effective_from'][:4]) or (policy.get('effective_until') and year > policy['effective_until'][:4]):
                    raise ValueError('政策生效范围不覆盖所选评选年度，请核对政策版本')
                if policy['missing_attachments'] or policy['conflicts']:
                    raise ValueError('政策附件缺失或条款冲突，不能继续判断')
            elif tool == 'read_profile':
                with engine.begin() as conn:
                    profile_record = store.profile(conn, user_id)
                    snapshot = profile_identity(conn, user_id, profile_record['payload'])
            elif tool == 'calculate_metrics':
                payload['metrics'] = calculate(snapshot, policy)
            elif tool == 'check_conditions':
                report = evaluate(snapshot, policy)
            elif tool == 'request_information':
                payload['pending'] = questions(report['missing'], policy, report.get('metrics'))
                payload['messages'].append({'role': 'assistant', 'text': '已读取政策和现有档案，还需要补充：' + '、'.join(q['label'] for q in payload['pending']) + '。补充后将继续本次评估。'})
                event['status'] = 'done'
                payload['partial'] = report
                checkpoint(payload, 'waiting')
                return
            elif tool == 'prepare_guidance':
                report['materials'] = policy['materials']
                report['steps'] = policy['steps']
            elif tool == 'review_assessment':
                for attempt in range(3):
                    issues = verify(report, snapshot, policy)
                    model_issues = llm.review(report, policy) if llm.enabled() else []
                    issues += model_issues
                    review_log.append({'round': attempt + 1, 'issues': issues, 'model_checked': llm.enabled()})
                    if not issues:
                        break
                    if attempt == 2:
                        raise ValueError('复核仍存在问题，结果未发布，需要人工核对')
                    report = evaluate(snapshot, policy)
            completed.add(tool)
            event['status'] = 'done'
            checkpoint(payload)
            if {'review_assessment', 'prepare_guidance'} <= completed:
                with engine.begin() as conn:
                    if store.profile(conn, user_id)['revision'] != profile_record['revision']:
                        raise ValueError('个人档案已更新，请重新评估')
                    # A policy change during execution invalidates this run.
                    live_policy = store.get(conn, store.policies, policy_record['id'])
                    if live_policy['status'] != 'active' or live_policy['revision'] != policy_record['revision']:
                        raise ValueError('政策已更新，请重新评估')
                    result = store.create(conn, store.assessments, user_id, {'session_id': session_id, 'report': report, 'policy_id': policy_record['id'],
                        'policy_snapshot': {k:v for k,v in policy.items() if k not in ('path', 'attachments')}, 'profile_snapshot': snapshot, 'reviews': review_log, 'tools': payload['tools'], 'mode': payload['mode']}, 'completed')
                    current = store.get(conn, store.sessions, session_id, user_id)
                    payload['assessment_id'] = result['id']
                    payload['partial'] = None
                    payload['messages'].append({'role': 'assistant', 'text': report['conclusion'] + '。逐项依据、计算结果、材料清单和待核实事项见报告。' + report['notice']})
                    store.save(conn, store.sessions, current, payload, 'completed')
                return
        raise ValueError('已达到本次 12 次工具调用上限，请重试或核对输入')
    except Exception as exc:
        # Keep internal exception details out of user-visible payloads.
        safe = str(exc) if isinstance(exc, ValueError) else '模型或工具暂时不可用，进度已保存，请重试。'
        payload['error'] = safe
        payload['reviews'] = review_log
        payload['messages'].append({'role': 'assistant', 'text': safe + ' 本轮未生成新的资格结论。'})
        checkpoint(payload, 'retryable')
