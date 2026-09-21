"""Import the 2025-2026 XJU national scholarship notice as a reviewable draft."""
from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.main import engine, users
from app.academic import store
from app.academic.documents import text_pages
from app.academic.schemas import PolicyDraft


COLLEGE_SUPPLEMENT = """学院补充要求（由用户提供，启用前须取得正式原件核对）：学院名额5人，普通类4人、单列类1人；学习成绩排名位于前10%；上学年挂科学生不可申报；违纪处分未解除学生不可申报；单科成绩不低于70分；体育成绩不低于80分；学生须在2026年9月8日19:00前提交电子材料。"""


def locate(clauses, keyword):
    return next((clause['id'] for clause in clauses if keyword in clause['text']), clauses[0]['id'])


def build_payload(document: Path):
    pages = text_pages(document.name, document.read_bytes())
    original = [{'locator': locator, 'text': text} for locator, text in pages if text.strip()]
    original.append({'locator': '用户提供的学院补充要求（待正式文件核对）', 'text': COLLEGE_SUPPLEMENT})
    clauses = [
        {'id': f'school-{index + 1}', 'locator': item['locator'], 'text': item['text'].strip()}
        for index, item in enumerate(original[:-1])
    ]
    clauses.append({'id': 'college-supplement', 'locator': original[-1]['locator'], 'text': COLLEGE_SUPPLEMENT})

    grade_clause = locate(clauses, '二年级以上')
    materials_clause = locate(clauses, '材料提交与报送')
    process_clause = locate(clauses, '时间安排')
    pe_clause = locate(clauses, '体育课成绩')
    supplement = 'college-supplement'

    draft = PolicyDraft(
        title='关于新疆工程学院2025-2026学年国家奖学金评选工作的通知',
        school='新疆工程学院',
        scholarship='国家奖学金',
        selection_year=2026,
        academic_year='2025-2026',
        audience='二年级及以上在校全日制本、专科学生',
        effective_from='2026-09-06',
        application_end='2026-09-08T19:00:00+08:00',
        clauses=clauses,
        common_rules=[
            {'id':'grade-level','label':'二年级及以上在校生','clause_id':grade_clause,'field':'grade_level','operator':'ge','value':2,'year_bound':False},
            {'id':'no-failed-course','label':'上学年无挂科','clause_id':supplement,'field':'failed_course_count','operator':'eq','value':0},
            {'id':'minimum-course-score','label':'单科成绩不低于70分','clause_id':supplement,'field':'min_course_score','operator':'ge','value':70},
            {'id':'physical-education','label':'体育成绩不低于80分','clause_id':supplement,'field':'pe_policy_score','operator':'ge','value':80,'year_bound':False},
            {'id':'discipline','label':'不存在未解除的违纪处分','clause_id':supplement,'field':'has_active_discipline','operator':'eq','value':False,'year_bound':False},
        ],
        materials=[
            {'text':'国家奖学金申请书（第一人称，电子版）','clause_id':materials_clause},
            {'text':'国家奖学金申请审批表','clause_id':materials_clause},
            {'text':'学院推荐材料（第三人称，电子版）','clause_id':materials_clause},
            {'text':'2025-2026学年学生成绩登记表','clause_id':materials_clause},
            {'text':'身份证及申报获奖对应证书扫描件','clause_id':materials_clause},
            {'text':'2寸免冠电子照片','clause_id':materials_clause},
            {'text':'国家奖学金获奖学生初审名单表','clause_id':materials_clause},
        ],
        steps=[
            {'text':'学生申请并由班级初步推荐，班内公示不少于1个工作日','clause_id':process_clause},
            {'text':'学院组织答辩和评审，确定拟推荐学生','clause_id':process_clause},
            {'text':'学院公示拟推荐学生不少于5个工作日','clause_id':process_clause},
            {'text':'党委学生工作部审核并提交学生工作委员会审议','clause_id':process_clause},
            {'text':'全校公示后报校长办公会审定','clause_id':process_clause},
        ],
        deadlines=[
            {'name':'学生向学院提交电子材料','due_at':'2026-09-08T19:00:00+08:00','audience':'student','clause_id':supplement},
            {'name':'学院确定拟推荐学生名单','due_at':'2026-09-18T23:59:59+08:00','audience':'college','clause_id':process_clause},
            {'name':'学院向学校报送电子材料','due_at':'2026-09-19T23:59:59+08:00','audience':'college','clause_id':materials_clause},
        ],
        quotas=[
            {'category':'普通类','count':4,'clause_id':supplement},
            {'category':'单列类','count':1,'clause_id':supplement},
        ],
        missing_attachments=[
            '新疆工程学院国家奖学金实施细则（校发〔2024〕24号）',
            '学院国家奖学金评选补充通知正式原件',
            '校级通知附件1至附件5',
        ],
        conflicts=[
            '学习成绩排名前10%的排名范围尚未明确，不能生成 academic_rank_ratio 规则',
            '现有材料未证明综合测评排名属于资格条件，不能据此追问或判定',
        ],
        reviewed=False,
    ).model_dump()
    return draft, original, pe_clause


def main():
    parser = argparse.ArgumentParser(description='导入新疆工程学院国家奖学金政策草稿')
    parser.add_argument('document', type=Path)
    parser.add_argument('--admin', required=True, help='已有管理员用户名')
    args = parser.parse_args()
    document = args.document.resolve()
    if not document.is_file():
        parser.error('通知文件不存在')
    if document.suffix.lower() != '.docx':
        parser.error('当前脚本要求 DOCX 通知文件')

    draft, original, _ = build_payload(document)
    identifier = str(uuid.uuid4())
    upload_root = Path(os.getenv('ACADEMIC_UPLOAD_DIR', Path(__file__).resolve().parents[1] / '.private' / 'academic'))
    upload_root.mkdir(parents=True, exist_ok=True)
    target = upload_root / f'{identifier}.docx'

    with engine.begin() as conn:
        admin = conn.execute(select(users).where(users.c.username == args.admin)).mappings().first()
        if not admin or admin['role'] != 'admin' or not admin['is_active']:
            parser.error('指定账号不存在、未启用或不是管理员')
        duplicate = next((row for row in store.listing(conn, store.policies) if all(row['payload'].get(key) == draft[key] for key in ('school','scholarship','selection_year','academic_year'))), None)
        if duplicate:
            parser.error(f"对应年度政策已存在：{duplicate['id']}（{duplicate['status']}）")
        payload = copy.deepcopy(draft)
        payload.update(filename=document.name, path=str(target), original=original, attachments=[])
        shutil.copyfile(document, target)
        try:
            record = store.create(conn, store.policies, admin['id'], payload, identifier=identifier)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    print(f"已创建政策草稿：{record['id']}")
    print('状态：draft；存在缺失附件和待确认冲突，不能直接启用。')
    print('下一步：在政策库中补充正式附件，确认排名范围，核对规则并将 reviewed 设为 true。')


if __name__ == '__main__':
    main()
