import copy
import hashlib
import json
import os
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from . import store, llm
from .schemas import ConfirmImport, ProfileUpdate, PolicyDraft, SessionCreate, Message, Fact, CourseCorrection, ClassRankingConfirm
from .documents import parse_transcript, text_pages, merge_courses, course_key
from .assistant import run
from .class_ranking import parse_score_image, annual_ranking

MAX_UPLOAD = 10 * 1024 * 1024


def register(app, engine, current):
    store.migrate(engine)
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        store.recover(engine)
        async with previous_lifespan(application) as state:
            yield state
    app.router.lifespan_context = lifespan
    router = APIRouter()

    def admin(user=Depends(current)):
        if user['role'] != 'admin':
            raise HTTPException(403, '仅管理员可管理政策')
        return user

    def ranking_manager(user=Depends(current)):
        if user['role'] not in ('admin', 'counselor'):
            raise HTTPException(403, '仅辅导员或管理员可处理班级成绩排名')
        return user

    async def upload(file, allowed):
        name = Path((file.filename or '').replace('\\', '/')).name
        if Path(name).suffix.lower() not in allowed:
            raise HTTPException(422, '不支持的文件格式')
        data = await file.read(MAX_UPLOAD + 1)
        await file.close()
        if not data or len(data) > MAX_UPLOAD:
            raise HTTPException(413, '文件为空或超过 10 MB')
        return name, data

    def file_path(identifier, suffix):
        root = Path(os.getenv('ACADEMIC_UPLOAD_DIR', str(Path(__file__).resolve().parents[2] / '.private' / 'academic')))
        root.mkdir(parents=True, exist_ok=True)
        return root / (identifier + suffix)

    def public_document(record):
        result = copy.deepcopy(record)
        result['payload'].pop('path', None)
        for attachment in result['payload'].get('attachments', []):
            attachment.pop('path', None)
        return result

    @router.post('/documents')
    async def import_document(file: UploadFile = File(...), user=Depends(current)):
        name, data = await upload(file, {'.pdf', '.xls', '.xlsx'})
        digest = hashlib.sha256(data).hexdigest()
        with engine.connect() as conn:
            duplicate = next((r for r in store.listing(conn, store.documents, user['id']) if r['payload']['hash'] == digest), None)
        if duplicate:
            return public_document(duplicate)
        identifier = str(uuid.uuid4())
        try:
            parsed = parse_transcript(name, data, identifier)
        except Exception:
            raise HTTPException(422, '文件无法解析，请确认未加密且格式正确')
        path = file_path(identifier, Path(name).suffix.lower())
        path.write_bytes(data)
        try:
            with engine.begin() as conn:
                result = store.create(conn, store.documents, user['id'], {'filename': name, 'hash': digest, 'path': str(path), 'preview': parsed}, identifier=identifier)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return public_document(result)

    @router.get('/documents')
    def list_documents(user=Depends(current)):
        with engine.connect() as conn:
            return [public_document(r) for r in store.listing(conn, store.documents, user['id'])]

    @router.get('/documents/{identifier}/file')
    def original_document(identifier: str, user=Depends(current)):
        with engine.connect() as conn:
            document = store.get(conn, store.documents, identifier, user['id'])
        return FileResponse(document['payload']['path'], filename=document['payload']['filename'], headers={'Cache-Control': 'no-store'})

    @router.post('/documents/{identifier}/confirm')
    def confirm(identifier: str, body: ConfirmImport, user=Depends(current)):
        with engine.begin() as conn:
            document = store.get(conn, store.documents, identifier, user['id'])
            profile = store.profile(conn, user['id'])
            incoming = body.model_dump()
            for item in [*incoming['courses'], *incoming['facts'].values()]:
                # Source ownership cannot be supplied by a client.
                item['sources'] = [{'document_id': identifier, 'filename': document['payload']['filename'],
                                    'locator': next((s['locator'] for s in item['sources'] if s.get('document_id') == identifier), '用户核对补录')}]
            data = copy.deepcopy(profile['payload'])
            data['courses'] = merge_courses(data['courses'], incoming['courses'])
            for key, value in incoming['facts'].items():
                existing = data['facts'].get(key)
                if existing and existing['value'] != value['value'] and existing.get('academic_year') == value.get('academic_year'):
                    raise HTTPException(409, f'{key} 与已确认档案冲突，请核对')
                value['confirmed'] = True
                if existing and existing['value'] == value['value']:
                    value['sources'] = existing['sources'] + [s for s in value['sources'] if s not in existing['sources']]
                if existing:
                    data.setdefault('fact_history', []).append({'field': key, **existing})
                data['facts'][key] = value
            store.save(conn, store.profiles, profile, data)
            store.save(conn, store.documents, document, document['payload'], 'confirmed')
        return {'status': 'confirmed', 'course_count': len(data['courses'])}

    @router.patch('/academic-profile/courses')
    def correct_course(body: CourseCorrection, user=Depends(current)):
        with engine.begin() as conn:
            profile = store.profile(conn, user['id'])
            if profile['revision'] != body.revision:
                raise HTTPException(409, '档案已变更，请刷新后重新核对')
            data = copy.deepcopy(profile['payload'])
            course = body.course.model_dump()
            index = next((i for i, c in enumerate(data['courses']) if course_key(c) == course_key(course)), None)
            if index is None:
                raise HTTPException(404, '课程不存在')
            previous = data['courses'][index]
            data.setdefault('corrections', []).append({'before': previous, 'reason': body.reason, 'at': store.now()})
            course['sources'] = previous['sources'] + [{'document_id': None, 'filename': '', 'locator': '用户确认更正：' + body.reason}]
            data['courses'][index] = course
            return store.save(conn, store.profiles, profile, data)

    @router.get('/academic-profile')
    def get_profile(user=Depends(current)):
        with engine.begin() as conn:
            return store.profile(conn, user['id'])

    def merge_facts(conn, user_id, facts):
        if len(facts) > 100:
            raise HTTPException(422, '一次最多补充 100 个字段')
        profile = store.profile(conn, user_id)
        data = copy.deepcopy(profile['payload'])
        for key, fact in facts.items():
            import re
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', key):
                raise HTTPException(422, '字段名格式错误')
            value = fact.model_dump()
            value['confirmed'] = True
            value['sources'] = [{'document_id': None, 'filename': '', 'locator': '用户确认补充 ' + store.now()}]
            if key in data['facts']:
                data.setdefault('fact_history', []).append({'field': key, **data['facts'][key]})
            data['facts'][key] = value
        return store.save(conn, store.profiles, profile, data)

    @router.patch('/academic-profile')
    def edit_profile(body: ProfileUpdate, user=Depends(current)):
        with engine.begin() as conn:
            return merge_facts(conn, user['id'], body.facts)

    @router.get('/class-rankings')
    def list_class_rankings(user=Depends(ranking_manager)):
        with engine.connect() as conn:
            return store.listing(conn, store.rankings, user['id'])

    @router.get('/class-rankings/{identifier}')
    def get_class_ranking(identifier: str, user=Depends(ranking_manager)):
        with engine.connect() as conn:
            return store.get(conn, store.rankings, identifier, user['id'])

    @router.post('/class-rankings')
    async def create_class_ranking(files: list[UploadFile] = File(...), academic_year: str = Form(...), class_name: str = Form(...), user=Depends(ranking_manager)):
        if not 2 <= len(files) <= 6:
            raise HTTPException(422, '请上传 2 至 6 张同一学年、同一班级的成绩单图片')
        sheets = []
        for index, file in enumerate(files, 1):
            name, data = await upload(file, {'.png', '.jpg', '.jpeg', '.webp'})
            try:
                sheets.append(parse_score_image(name, data, academic_year=academic_year, term=index, class_name=class_name))
            except Exception as exc:
                raise HTTPException(422, f'{name} 识别失败：{exc}')
        try:
            ranking = annual_ranking(sheets)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        payload = {'sheets': sheets, 'ranking': ranking, 'rank_method': 'competition',
                   'notice': 'OCR 结果必须人工核对后确认；未完整出现在全部学期的学生不参与正式排名。'}
        with engine.begin() as conn:
            return store.create(conn, store.rankings, user['id'], payload, 'draft')

    @router.put('/class-rankings/{identifier}')
    def confirm_class_ranking(identifier: str, body: ClassRankingConfirm, user=Depends(ranking_manager)):
        try:
            ranking = annual_ranking([sheet.model_dump() for sheet in body.sheets])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        with engine.begin() as conn:
            record = store.get(conn, store.rankings, identifier, user['id'])
            payload = copy.deepcopy(record['payload'])
            payload.update(sheets=[sheet.model_dump() for sheet in body.sheets], ranking=ranking, rank_method=body.rank_method,
                           confirmed_at=store.now(), notice='排名已由经办人核对确认；结果仍以教务系统正式数据为准。')
            return store.save(conn, store.rankings, record, payload, 'confirmed')

    @router.get('/policies')
    def list_policies(user=Depends(current)):
        with engine.connect() as conn:
            rows = store.listing(conn, store.policies)
        return [public_document(r) for r in rows if user['role'] == 'admin' or r['status'] == 'active']

    @router.post('/policies')
    async def import_policy(file: UploadFile = File(...), metadata: str = Form(...), user=Depends(admin)):
        name, data = await upload(file, {'.pdf', '.docx', '.txt', '.md', '.xls', '.xlsx'})
        try:
            draft = PolicyDraft.model_validate_json(metadata)
            pages = text_pages(name, data)
        except Exception:
            raise HTTPException(422, '政策元数据或原文格式错误')
        if not any(text.strip() for _, text in pages):
            raise HTTPException(422, '未提取到政策正文，暂不支持扫描件 OCR')
        identifier = str(uuid.uuid4())
        path = file_path(identifier, Path(name).suffix.lower())
        payload = draft.model_dump()
        payload.update(filename=name, path=str(path), original=[{'locator': loc, 'text': text} for loc, text in pages], reviewed=False)
        payload['clauses'] = [{'id': f'clause-{i+1}', 'locator': loc, 'text': text.strip()} for i, (loc, text) in enumerate(pages) if text.strip()]
        # Upload creates an unreviewed draft, never trusts caller-supplied rules.
        payload.update(common_rules=[], branches=[], materials=[], steps=[])
        path.write_bytes(data)
        try:
            with engine.begin() as conn:
                result = store.create(conn, store.policies, user['id'], payload, identifier=identifier)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return public_document(result)

    @router.post('/policies/{identifier}/attachments')
    async def policy_attachment(identifier: str, file: UploadFile = File(...), user=Depends(admin)):
        name, content = await upload(file, {'.pdf', '.docx', '.txt', '.md', '.xls', '.xlsx'})
        try:
            pages = text_pages(name, content)
        except Exception:
            raise HTTPException(422, '附件解析失败')
        if not any(t.strip() for _, t in pages):
            raise HTTPException(422, '附件没有可提取的文本')
        file_id = str(uuid.uuid4())
        path = file_path(file_id, Path(name).suffix.lower())
        path.write_bytes(content)
        try:
            with engine.begin() as conn:
                record = store.get(conn, store.policies, identifier)
                if record['status'] != 'draft':
                    raise HTTPException(409, '只能向草稿添加附件')
                payload = copy.deepcopy(record['payload'])
                payload.setdefault('attachments', []).append({'id': file_id, 'filename': name, 'path': str(path)})
                for i, (loc, text) in enumerate(pages):
                    locator = name + ' / ' + loc
                    payload['original'].append({'locator': locator, 'text': text})
                    if text.strip():
                        payload['clauses'].append({'id': f'{file_id}-{i}', 'locator': locator, 'text': text.strip()})
                payload['reviewed'] = False
                result = store.save(conn, store.policies, record, payload)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return public_document(result)

    @router.get('/policies/{identifier}/file')
    def policy_file(identifier: str, user=Depends(current)):
        with engine.connect() as conn:
            record = store.get(conn, store.policies, identifier)
        if record['status'] != 'active' and user['role'] != 'admin':
            raise HTTPException(404, '政策不存在')
        return FileResponse(record['payload']['path'], filename=record['payload']['filename'])

    @router.put('/policies/{identifier}')
    def update_policy(identifier: str, body: PolicyDraft, user=Depends(admin)):
        with engine.begin() as conn:
            record = store.get(conn, store.policies, identifier)
            if record['status'] != 'draft':
                raise HTTPException(409, '已启用版本不可修改，请导入新版本')
            original = record['payload']['original']
            for clause in body.clauses:
                if not any(clause.locator == p['locator'] and clause.text in p['text'] for p in original):
                    raise HTTPException(422, '条款必须逐字引用原文并保留正确位置')
            payload = dict(record['payload'], **body.model_dump())
            return public_document(store.save(conn, store.policies, record, payload))

    @router.post('/policies/{identifier}/extract')
    def extract_policy(identifier: str, user=Depends(admin)):
        if not llm.enabled():
            raise HTTPException(503, '未配置模型，可在规则编辑器手动填写')
        with engine.connect() as conn:
            record = store.get(conn, store.policies, identifier)
        if record['status'] != 'draft':
            raise HTTPException(409, '只能提取草稿政策')
        try:
            result = llm.call_structured('draft_policy', '对照提供的政策生成规则草稿。保留元数据和原文条款。未知项列入 conflicts；不得补造条件。排名比例使用 0 到 1，field 采用 academic_rank_ratio 或 comprehensive_rank_ratio。公共条件为 AND，branches 为 OR 且分支内部为 AND。',
                {'draft_json': {'type': 'string', 'description': '符合所给 PolicyDraft schema 的 JSON 字符串'}}, ['draft_json'],
                {'policy': {k:v for k,v in record['payload'].items() if k != 'path'}, 'schema': PolicyDraft.model_json_schema()})
            draft = PolicyDraft.model_validate_json(result['draft_json'])
            draft.reviewed = False
            return {'draft': draft.model_dump(), 'message': '仅为草稿，请对照原文核对后保存并启用'}
        except Exception:
            raise HTTPException(502, '模型未生成有效草稿，可手动核对和编辑')

    @router.post('/policies/{identifier}/activate')
    def activate(identifier: str, user=Depends(admin)):
        with engine.begin() as conn:
            record = store.get(conn, store.policies, identifier)
            payload = record['payload']
            if record['status'] != 'draft':
                raise HTTPException(409, '只能启用草稿')
            if not payload['reviewed'] or not (payload['common_rules'] or payload['branches']) or payload['missing_attachments'] or payload['conflicts']:
                raise HTTPException(422, '须核对完整规则并解决附件缺失及条款冲突，才能启用')
            if not payload['materials'] or not payload['steps']:
                raise HTTPException(422, '请补充带条款依据的材料清单与办理流程')
            for previous in store.listing(conn, store.policies):
                if previous['status'] == 'active' and all(previous['payload'][k] == payload[k] for k in ('school', 'scholarship', 'selection_year', 'academic_year')):
                    store.save(conn, store.policies, previous, previous['payload'], 'superseded')
            return public_document(store.save(conn, store.policies, record, payload, 'active'))

    @router.get('/assistant/sessions')
    def list_sessions(user=Depends(current)):
        with engine.connect() as conn:
            return store.listing(conn, store.sessions, user['id'])

    @router.post('/assistant/sessions')
    def new_session(body: SessionCreate, user=Depends(current)):
        with engine.begin() as conn:
            return store.create(conn, store.sessions, user['id'], {'context': body.model_dump(), 'messages': [], 'pending': [], 'tools': [], 'assessment_id': None}, 'ready')

    @router.get('/assistant/sessions/{identifier}')
    def get_session(identifier: str, user=Depends(current)):
        with engine.connect() as conn:
            return store.get(conn, store.sessions, identifier, user['id'])

    @router.post('/assistant/sessions/{identifier}/messages')
    def message(identifier: str, body: Message, background: BackgroundTasks, user=Depends(current)):
        with engine.begin() as conn:
            record = store.get(conn, store.sessions, identifier, user['id'])
            if record['status'] == 'running':
                raise HTTPException(409, '评估正在进行，请等待')
            if body.facts:
                merge_facts(conn, user['id'], body.facts)
            payload = copy.deepcopy(record['payload'])
            payload['messages'].append({'role': 'user', 'text': body.text or ('已确认补充信息' if body.facts else '继续评估'), 'at': store.now(), 'facts_submitted': bool(body.facts)})
            for key in ('selection_year', 'academic_year'):
                if getattr(body, key) is not None:
                    payload['context'][key] = getattr(body, key)
            payload['assessment_id'] = None
            result = store.save(conn, store.sessions, record, payload, 'running')
        background.add_task(run, engine, identifier, user['id'])
        return result

    @router.post('/assistant/sessions/{identifier}/interpret')
    def interpret(identifier: str, body: Message, user=Depends(current)):
        with engine.connect() as conn:
            record = store.get(conn, store.sessions, identifier, user['id'])
        if not llm.enabled():
            raise HTTPException(503, '请通过补充信息表单填写；未配置模型')
        pending = record['payload']['pending']
        try:
            args = llm.call_structured('suggest_facts', '从用户回复提取待补充字段，未知不填。排名值必须包括 rank、total、scope、type；不能推断排名范围。只建议，不写入档案。',
                {'facts_json': {'type': 'string'}}, ['facts_json'], {'pending': pending, 'reply': body.text, 'fact_schema': Fact.model_json_schema()})
            values = json.loads(args['facts_json'])
            if not isinstance(values, dict) or set(values) - {q['field'] for q in pending}:
                raise ValueError('非待补充字段')
            return {'suggestions': {k: Fact.model_validate(v).model_dump() for k, v in values.items()}, 'requires_confirmation': True}
        except Exception:
            raise HTTPException(502, '未能可靠提取，请使用表单补充')

    @router.get('/assessments')
    def list_assessments(user=Depends(current)):
        with engine.connect() as conn:
            return store.listing(conn, store.assessments, user['id'])

    @router.get('/assessments/{identifier}')
    def assessment(identifier: str, user=Depends(current)):
        with engine.connect() as conn:
            return store.get(conn, store.assessments, identifier, user['id'])

    app.include_router(router)
