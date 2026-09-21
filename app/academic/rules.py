"""Deterministic three-valued policy evaluation; no eval or model arithmetic."""
from decimal import Decimal
from datetime import datetime, time, timezone, timedelta

METRICS = {
    'average', 'weighted_average', 'total_credits', 'total_score', 'course_count',
    'failed_course_count', 'min_course_score', 'pe_policy_score', 'grade_level',
}
TRANSCRIPT_METRICS = METRICS - {'grade_level'}


def fact_for(profile, key, year=None):
    candidates = [profile['facts'].get(key, {})] + [f for f in reversed(profile.get('fact_history', [])) if f['field'] == key]
    return next((f for f in candidates if f and (year is None or f.get('academic_year') == year)), {})


def fact_value(profile, key, default=None):
    fact = fact_for(profile, key)
    return fact.get('value', default) if fact.get('confirmed') else default


def grade_level(profile, policy):
    value = fact_value(profile, 'grade_level')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    grade = fact_value(profile, 'grade')
    labels = {'大一': 1, '大二': 2, '大三': 3, '大四': 4, '研一': 1, '研二': 2, '研三': 3}
    if grade in labels:
        return labels[grade]
    admission_year = fact_value(profile, 'admission_year')
    if isinstance(admission_year, str) and admission_year.isdigit():
        admission_year = int(admission_year)
    if isinstance(admission_year, int):
        return policy['selection_year'] - admission_year + 1
    return None


def pe_policy_year(profile):
    admission_year = fact_value(profile, 'admission_year')
    if isinstance(admission_year, str) and admission_year.isdigit():
        admission_year = int(admission_year)
    target_years = {2025: '2025-2026', 2024: '2025-2026', 2023: '2024-2025'}
    return target_years.get(admission_year)


def pe_policy_courses(profile):
    target_year = pe_policy_year(profile)
    if not target_year:
        return []
    return [
        course for course in profile['courses']
        if course['academic_year'] == target_year
        and ('体育' in course.get('name', '') or '体育' in course.get('category', ''))
    ]


def calculate(profile, policy):
    year = policy['academic_year']
    courses = [c for c in profile['courses'] if c['academic_year'] == year and (not policy['course_categories'] or c['category'] in policy['course_categories'])]
    D = lambda value: Decimal(str(value))
    scores = sum((D(c['score']) for c in courses), Decimal(0))
    credits_known = bool(courses) and all(c['credits'] is not None for c in courses)
    credits = sum((D(c['credits']) for c in courses), Decimal(0)) if credits_known else None
    weighted = sum((D(c['credits']) * D(c['score']) for c in courses), Decimal(0)) / credits if credits else None
    pe_courses = pe_policy_courses(profile)
    pe_year = pe_policy_year(profile)
    pe_fact = fact_for(profile, 'physical_education', pe_year) if pe_year else {}
    pe_fact_value = pe_fact.get('value') if pe_fact.get('confirmed') else None
    try:
        pe_fact_score = D(pe_fact_value) if pe_fact_value is not None else None
    except (TypeError, ValueError, ArithmeticError):
        pe_fact_score = None
    grade_fact = fact_for(profile, 'grade_level') or fact_for(profile, 'grade') or fact_for(profile, 'admission_year')
    course_evidence = [source for course in courses for source in course['sources']]
    pe_evidence = [source for course in pe_courses for source in course['sources']] or pe_fact.get('sources', [])
    metric_inputs = {
        'average': courses,
        'weighted_average': courses,
        'total_credits': courses,
        'total_score': courses,
        'course_count': courses,
        'failed_course_count': courses,
        'min_course_score': courses,
        'pe_policy_score': pe_courses,
        'grade_level': [],
    }
    metric_evidence = {field: course_evidence for field in metric_inputs}
    metric_evidence['pe_policy_score'] = pe_evidence
    metric_evidence['grade_level'] = grade_fact.get('sources', [])
    complete = fact_for(profile, 'transcript_complete', year)
    known = complete.get('confirmed') and complete.get('value') is True and complete.get('academic_year') == year
    category_known = not policy['course_categories'] or all(c.get('category') for c in profile['courses'] if c['academic_year'] == year)
    failed_courses = [course for course in courses if D(course['score']) < Decimal('60')]
    pe_score = max((D(course['score']) for course in pe_courses), default=pe_fact_score)
    minimum_score = min((D(course['score']) for course in courses), default=None)
    level = grade_level(profile, policy)
    return {'academic_year': year, 'complete': bool(known and category_known and courses), 'course_count': len(courses), 'total_score': float(scores),
            'average': float(scores / len(courses)) if courses else None, 'total_credits': float(credits) if credits is not None else None,
            'weighted_average': float(weighted) if weighted is not None else None,
            'failed_course_count': len(failed_courses), 'min_course_score': float(minimum_score) if minimum_score is not None else None,
            'pe_policy_score': float(pe_score) if pe_score is not None else None, 'pe_policy_academic_year': pe_year,
            'grade_level': level,
            'formulas': {'average': 'Σ成绩 / 课程数', 'weighted_average': 'Σ(成绩×学分) / Σ学分', 'total_credits': 'Σ学分', 'total_score': 'Σ成绩',
                         'failed_course_count': '成绩 < 60 的课程数', 'min_course_score': '所有考核课程中的最低成绩',
                         'pe_policy_score': '按年级口径选择体育课程后的最高成绩'},
            'inputs': courses, 'metric_inputs': metric_inputs, 'metric_evidence': metric_evidence, 'course_categories': policy['course_categories']}


def condition(rule, profile, policy, metrics):
    field = rule['field']
    missing, evidence, actual = [], [], None
    if field in METRICS:
        if field in TRANSCRIPT_METRICS and not metrics['complete']:
            missing.append('transcript_complete')
        if metrics.get(field) is None:
            missing.append('course_credits' if field in ('weighted_average', 'total_credits') else 'physical_education' if field == 'pe_policy_score' else 'courses' if field != 'grade_level' else 'grade_level')
        actual = metrics.get(field)
        evidence = metrics.get('metric_evidence', {}).get(field, [])
    else:
        fact_key = field.removesuffix('_ratio') if field.endswith('_rank_ratio') else field
        fact = fact_for(profile, fact_key, policy['academic_year'] if rule['year_bound'] else None)
        if not fact.get('confirmed') or (rule['year_bound'] and fact.get('academic_year') != policy['academic_year']):
            missing.append(fact_key)
        else:
            actual = fact.get('value')
            evidence = fact.get('sources', [])
            if field.endswith('_rank_ratio'):
                value = actual
                if (not isinstance(value, dict) or type(value.get('rank')) is not int or type(value.get('total')) is not int
                        or not 1 <= value['rank'] <= value['total'] or value.get('scope') != rule['scope'] or value.get('type') != fact_key):
                    missing.append(fact_key)
                    actual = None
                else:
                    actual = float(Decimal(value['rank']) / Decimal(value['total']))
    status = 'unknown'
    if actual is None and not missing:
        missing.append(field)
    if not missing:
        expected, op = rule['value'], rule['operator']
        try:
            if op in ('le', 'lt', 'ge', 'gt'):
                if type(actual) not in (int, float):
                    raise ValueError('需要数值')
                a, b = Decimal(str(actual)), Decimal(str(expected))
                passed = {'le': a <= b, 'lt': a < b, 'ge': a >= b, 'gt': a > b}[op]
            elif op == 'eq':
                passed = actual == expected and (isinstance(actual, bool) == isinstance(expected, bool))
            else:
                passed = actual in expected
            status = 'pass' if passed else 'fail'
        except (TypeError, ValueError, ArithmeticError):
            missing.append(field)
    return {'rule_id': rule['id'], 'label': rule['label'], 'field': field, 'operator': rule['operator'], 'expected': rule['value'],
            'actual': actual, 'status': status, 'missing': missing, 'evidence': evidence,
            'clause': next(c for c in policy['clauses'] if c['id'] == rule['clause_id'])}


def conjunction(rows):
    return 'fail' if any(r['status'] == 'fail' for r in rows) else 'unknown' if any(r['status'] == 'unknown' for r in rows) else 'pass'


def evaluate(profile, policy):
    metrics = calculate(profile, policy)
    common = [condition(r, profile, policy, metrics) for r in policy['common_rules']]
    branches = [{'id': b['id'], 'label': b['label'], 'conditions': [condition(r, profile, policy, metrics) for r in b['rules']]} for b in policy['branches']]
    for b in branches:
        b['status'] = conjunction(b['conditions'])
    common_status = conjunction(common)
    branch_status = 'pass' if not branches or any(b['status'] == 'pass' for b in branches) else 'unknown' if any(b['status'] == 'unknown' for b in branches) else 'fail'
    status = conjunction([{'status': common_status}, {'status': branch_status}])
    # A satisfied alternative makes missing inputs in other alternatives optional.
    required = common + ([r for b in branches if b['status'] != 'fail' for r in b['conditions']] if branch_status != 'pass' else [])
    missing = sorted({f for r in required for f in r['missing']})
    zone = timezone(timedelta(hours=8))
    current = datetime.now(zone)

    def boundary(value, end_of_day=False):
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone)
        if end_of_day and 'T' not in value and ' ' not in value:
            parsed = datetime.combine(parsed.date(), time.max, tzinfo=zone)
        return parsed.astimezone(zone)

    start = boundary(policy.get('application_start'))
    end = boundary(policy.get('application_end'), end_of_day=True)
    student_deadlines = [boundary(item['due_at']) for item in policy.get('deadlines', []) if item.get('audience') == 'student']
    if student_deadlines:
        end = min(student_deadlines) if end is None else min([end, *student_deadlines])
    window = 'unknown' if not end and not start else 'not_started' if start and current < start else 'closed' if end and current > end else 'open'
    return {'status': status, 'conclusion': {'pass': '初步符合', 'fail': '存在不满足条件', 'unknown': '信息不足'}[status],
            'common_conditions': common, 'branches': branches, 'metrics': metrics, 'missing': missing,
            'materials': policy['materials'], 'steps': policy['steps'], 'deadlines': policy.get('deadlines', []),
            'quotas': policy.get('quotas', []), 'application_window': window,
            'notice': '这是基于已提供材料的资格初评，最终结果以学校审核为准。'}


def verify(report, profile, policy):
    expected = evaluate(profile, policy)
    issues = [f'{key} 与规则计算不一致' for key in expected if report.get(key) != expected[key]]
    for row in report.get('common_conditions', []) + [r for b in report.get('branches', []) for r in b['conditions']]:
        if row['status'] == 'pass' and not row['evidence']:
            issues.append(f"{row['label']}缺少个人事实来源")
    return issues
