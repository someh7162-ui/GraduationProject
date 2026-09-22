from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, uuid, re, logging, math
from collections import OrderedDict
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, Boolean, select, inspect, text
# Bound BLAS startup threads for the lightweight campus workload.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
from app.catalog.xjie_academics import resolve_student_selection
from app.recommendation import content_visible, rank_contents, match_summary
from app.source_metadata import content_active, source_details
from app.rag_index import RagIndex
from app.settings import jwt_secret, cors_origins
from app.content_types import normalize_type, CONTENT_TYPES
from app import jev
ROOT=Path(__file__).resolve().parents[1]; STATIC=ROOT/'frontend'
load_dotenv(ROOT / '.env')
logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
logger=logging.getLogger(__name__)
SECRET=jwt_secret()
def url():
    if os.getenv('DATABASE_URL'): return os.getenv('DATABASE_URL')
    if os.getenv('MYSQL_PASSWORD') is not None: return f"mysql+pymysql://{os.getenv('MYSQL_USER','root')}:{os.getenv('MYSQL_PASSWORD')}@{os.getenv('MYSQL_HOST','127.0.0.1')}:{os.getenv('MYSQL_PORT','3306')}/{os.getenv('MYSQL_DB','campus_recommender')}?charset=utf8mb4"
    return f"sqlite:///{os.getenv('CAMPUS_DB',ROOT/'campus.db')}"
engine=create_engine(url(),future=True,pool_pre_ping=True); md=MetaData()
users=Table('users',md,Column('id',Integer,primary_key=True),Column('username',String(80),unique=True),Column('name',String(120)),Column('password_hash',String(255)),Column('role',String(30)),Column('college',String(120)),Column('college_code',String(80)),Column('major',String(120)),Column('major_code',String(30)),Column('grade',String(30)),Column('class_name',String(120)),Column('managed_classes',Text,default='[]'),Column('interests',Text,default='[]'),Column('onboarding_completed',Boolean,default=False),Column('is_active',Boolean,default=True),Column('created_at',String(40)))
contents=Table('contents',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('title',String(200)),Column('body',Text),Column('summary',Text),Column('content_type',String(40)),Column('publisher_id',Integer),Column('target_roles',Text,default='[]'),Column('target_colleges',Text,default='[]'),Column('target_majors',Text,default='[]'),Column('target_grades',Text,default='[]'),Column('tags',Text,default='[]'),Column('source_url',String(500)),Column('source_site',String(200)),Column('source_department',String(200)),Column('source_id',String(200)),Column('content_hash',String(64)),Column('source_type',String(40),default='unknown'),Column('source_authority',String(200)),Column('last_verified_at',String(40)),Column('effective_from',String(40)),Column('effective_to',String(40)),Column('crawl_time',String(40)),Column('updated_at',String(40)),Column('start_time',String(40)),Column('end_time',String(40)),Column('publish_time',String(40)),Column('status',String(30),default='published'))
knowledge_documents=Table('knowledge_documents',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('source_content_id',Integer),Column('chunk_index',Integer,nullable=False),Column('title',String(200),nullable=False),Column('chunk_text',Text,nullable=False),Column('content_type',String(40)),Column('target_roles',Text,default='[]'),Column('target_colleges',Text,default='[]'),Column('target_majors',Text,default='[]'),Column('target_grades',Text,default='[]'),Column('publish_time',String(40)),Column('source_url',String(500)),Column('embedding',Text,default='[]'),Column('embed_model',String(120),default='tfidf-char-2-4'),Column('content_hash',String(64),unique=True),Column('created_at',String(40)))
events=Table('user_events',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('user_id',Integer),Column('content_id',Integer),Column('event_type',String(40)),Column('source',String(40)),Column('timestamp',String(40)))
feedbacks=Table('feedbacks',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('user_id',Integer),Column('content_id',Integer),Column('feedback_type',String(40)),Column('reason',Text),Column('created_at',String(40)))
modules=Table('interest_modules',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('name',String(80),unique=True),Column('description',String(255)),Column('icon',String(20)),Column('recommended_grades',Text),Column('recommended_roles',Text),Column('sort_order',Integer))
user_modules=Table('user_interests',md,Column('user_id',Integer,primary_key=True),Column('module_id',Integer,primary_key=True),Column('created_at',String(40)))
app=FastAPI(title='校园信息推荐系统'); app.add_middleware(CORSMiddleware,allow_origins=cors_origins(),allow_methods=['*'],allow_headers=['*'])
def now(): return datetime.now(timezone.utc).isoformat()
def pj(v):
    try: x=json.loads(v or '[]') if isinstance(v,str) else v; return x if isinstance(x,list) else []
    except: return []
def jt(v): return json.dumps(v or [],ensure_ascii=False)
RAG_REFUSAL='未找到可靠的校园资料，请尝试更具体的关键词，或联系辅导员。'
_answer_cache=OrderedDict(); _answer_cache_lock=__import__('threading').Lock()
def hp(v):
    s=secrets.token_bytes(16); d=hashlib.pbkdf2_hmac('sha256',v.encode(),s,180000); return 'p$'+base64.urlsafe_b64encode(s).decode()+'$'+base64.urlsafe_b64encode(d).decode()
def vp(v,e):
    try: _,s,d=e.split('$'); return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',v.encode(),base64.urlsafe_b64decode(s),180000),base64.urlsafe_b64decode(d))
    except: return False
def token(i): return jwt.encode({'sub':str(i),'exp':datetime.now(timezone.utc)+timedelta(hours=24)},SECRET,algorithm='HS256')
def pub(r):
    d=dict(r); d['interests']=pj(d.get('interests')); d['managed_classes']=pj(d.get('managed_classes')); d.pop('password_hash',None); return d
def cpub(r):
    d=dict(r)
    d['content_type'] = normalize_type(d.get('content_type'))
    for k in ('target_roles','target_colleges','target_majors','target_grades','tags'): d[k]=pj(d.get(k))
    return d
def parse_dt(v):
    if not v: return None
    try: return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception: return None
def deadline_info(v):
    d=parse_dt(v); n=datetime.now(timezone.utc)
    if not d: return 'normal',None,0.0
    days=(d-n).total_seconds()/86400
    if days < 0: return 'expired',math.floor(days),0.0
    if days <= 1: return 'today',math.ceil(days),1.0
    if days <= 3: return 'ending_soon',math.ceil(days),0.7
    return 'normal',math.ceil(days),0.0
SEEDS=['新生入学','校园生活','社团活动','志愿服务','学习成长','创新创业','奖助学金','心理健康','就业实习','考研升学','活动运营','班级管理']
def _ensure_unique_hash(c):
    """DB-level guard so identical content can never be imported twice.

    Works on both SQLite and MySQL; if legacy duplicates already exist the
    index cannot be built and we only log a warning instead of failing boot.
    """
    if not inspect(c).has_table('contents'): return
    if any(ix['name'] == 'uq_contents_content_hash' for ix in inspect(c).get_indexes('contents')): return
    try:
        c.execute(text('CREATE UNIQUE INDEX uq_contents_content_hash ON contents (content_hash)'))
        logger.info('unique index created on contents.content_hash')
    except Exception as ex:
        logger.warning('skip unique index on contents.content_hash: %s', ex)

def init_db():
    with engine.begin() as c:
        md.create_all(c)
        # Upgrade the original SQLite schema in-place when running without MySQL.
        if inspect(c).has_table('users'):
            cols={x['name'] for x in inspect(c).get_columns('users')}
            for name, ddl in {'username':'VARCHAR(80)','password_hash':'VARCHAR(255)','college_code':'VARCHAR(80)','major_code':'VARCHAR(30)','class_name':'VARCHAR(120)','managed_classes':'TEXT','onboarding_completed':'BOOLEAN DEFAULT 0','is_active':'BOOLEAN DEFAULT 1'}.items():
                if name not in cols: c.execute(text(f'ALTER TABLE users ADD COLUMN {name} {ddl}'))
            for row in c.execute(select(users.c.id, users.c.college, users.c.major, users.c.college_code, users.c.major_code)).mappings():
                if row.get('college_code') and row.get('major_code'):
                    continue
                try:
                    college, major = resolve_student_selection(row.get('college'), row.get('major'))
                except ValueError:
                    continue
                c.execute(users.update().where(users.c.id == row['id']).values(college=college['name'], college_code=college['code'], major=major['name'], major_code=major['code']))
        if inspect(c).has_table('contents'):
            cols={x['name'] for x in inspect(c).get_columns('contents')}
            additions={'target_grades':'TEXT','summary':'TEXT','target_majors':'TEXT','source_url':'VARCHAR(500)','source_site':'VARCHAR(200)','source_department':'VARCHAR(200)','source_id':'VARCHAR(200)','content_hash':'VARCHAR(64)','crawl_time':'VARCHAR(40)','updated_at':'VARCHAR(40)','source_type':'VARCHAR(40)','source_authority':'VARCHAR(200)','last_verified_at':'VARCHAR(40)','effective_from':'VARCHAR(40)','effective_to':'VARCHAR(40)'}
            for name,ddl in additions.items():
                if name not in cols: c.execute(text(f'ALTER TABLE contents ADD COLUMN {name} {ddl}'))
        if c.execute(select(modules.c.id)).first() is None: c.execute(modules.insert(),[{'name':n,'description':f'{n}相关校园信息','icon':'✦','recommended_grades':jt(['大一'] if n=='新生入学' else (['大四'] if n in ['就业实习','考研升学'] else [])),'recommended_roles':jt(['counselor'] if n=='班级管理' else (['organizer'] if n=='活动运营' else ['student'])),'sort_order':i} for i,n in enumerate(SEEDS)])
        for value in c.execute(select(contents.c.content_type).distinct()).scalars().all():
            canonical = normalize_type(value)
            if value != canonical:
                c.execute(contents.update().where(contents.c.content_type == value).values(content_type=canonical))
        _ensure_unique_hash(c)
        if c.execute(select(users.c.id).limit(1)).first() is None:
            c.execute(users.insert(),[{'username':'legacy_admin','name':'历史管理员','password_hash':None,'role':'admin','college':'','major':'','grade':'','interests':'[]','onboarding_completed':False,'is_active':False,'created_at':now()}])
            p=c.execute(select(users.c.id)).scalar_one(); data=[('新生入学报到指南','大一新生报到流程、校园卡领取、宿舍入住和军训安排。','notice',['student'],['大一'],['新生入学','校园生活']),('大四就业与实习双选会','面向大四学生的秋季就业双选会，提供简历诊断和现场面试。','activity',['student'],['大四'],['就业实习','就业']),('校园创新创业讲座','分享项目孵化、商业计划书和竞赛经验。','lecture',['student'],[],['创新创业']),('奖学金申请通知','本年度奖学金申请开始，请提交申请材料。','notice',['student'],[],['奖助学金']),('校园志愿服务招募','招募志愿者参与校园志愿服务。','activity',['student'],[],['志愿服务'])]
            c.execute(contents.insert(),[{'title':t,'body':b,'summary':b[:160],'content_type':typ,'publisher_id':p,'target_roles':jt(r),'target_colleges':'[]','target_majors':'[]','target_grades':jt(g),'tags':jt(tags),'publish_time':now(),'end_time':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(),'status':'published'} for t,b,typ,r,g,tags in data])
init_db()
_rag_index = RagIndex(engine, contents, knowledge_documents)
class Reg(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r'^[A-Za-z0-9_]+$')
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)
    role: Literal['student'] = 'student'
    college: str = Field(min_length=1, max_length=120)
    major: str = Field(min_length=1, max_length=120)
    grade: Literal['大一', '大二', '大三', '大四']
class Login(BaseModel): username:str; password:str
class Interests(BaseModel): module_ids:list[int]=Field(min_length=3,max_length=8)
class Event(BaseModel):
    content_id: int
    event_type: Literal['view', 'click', 'favorite', 'share', 'register', 'dismiss']
    source: str = Field(default='homepage', max_length=40)
class Ask(BaseModel): question:str=Field(min_length=2,max_length=500)
class Explain(BaseModel): content_id:int
def current(auth: str|None=Header(default=None, alias='Authorization')):
    try: p=jwt.decode((auth or '').removeprefix('Bearer '),SECRET,algorithms=['HS256']); i=int(p['sub'])
    except: raise HTTPException(401,'请先登录')
    with engine.connect() as c:r=c.execute(select(users).where(users.c.id==i)).mappings().first()
    if not r or r.get('is_active') is False: raise HTTPException(401,'用户不存在或已停用')
    return dict(r)
@app.get('/')
def index():
    b=STATIC/'dist'/'index.html'; return FileResponse(b if b.exists() else STATIC/'index.html')
if (STATIC/'dist'/'assets').exists(): app.mount('/assets',StaticFiles(directory=STATIC/'dist'/'assets'),name='assets')
@app.post('/auth/register')
def register(x:Reg):
    try:
        college, selected_major = resolve_student_selection(x.college, x.major)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with engine.begin() as c:
        if c.execute(select(users.c.id).where(users.c.username==x.username)).first(): raise HTTPException(409,'用户名已存在')
        i=c.execute(users.insert().values(username=x.username,name=x.name.strip(),password_hash=hp(x.password),role='student',college=college['name'],college_code=college['code'],major=selected_major['name'],major_code=selected_major['code'],grade=x.grade,interests='[]',onboarding_completed=False,is_active=True,created_at=now())).inserted_primary_key[0]
    return {'message':'注册成功，请登录','user_id':i}
@app.post('/auth/login')
def login(x:Login):
    with engine.connect() as c:r=c.execute(select(users).where(users.c.username==x.username)).mappings().first()
    if not r or r.get('is_active') is False or not vp(x.password,r['password_hash']): raise HTTPException(401,'用户名或密码错误')
    return {'access_token':token(r['id']),'token_type':'bearer','user':pub(r)}
@app.post('/auth/logout')
def logout(u=Depends(current)): return {'status':'logged_out'}
@app.get('/me')
def me(u=Depends(current)): return pub(u)
@app.get('/onboarding/modules')
def get_modules(u=Depends(current)):
    with engine.connect() as c: rs=c.execute(select(modules).order_by(modules.c.sort_order)).mappings().all()
    return [dict(r) for r in rs]
@app.get('/onboarding/status')
def onboarding_status(u=Depends(current)): return {'completed':bool(u['onboarding_completed']),'selected':pj(u['interests'])}
@app.post('/onboarding/interests')
def save_interests(x:Interests,u=Depends(current)):
    with engine.begin() as c:
        rs=c.execute(select(modules).where(modules.c.id.in_(x.module_ids))).mappings().all()
        if len(rs)!=len(set(x.module_ids)): raise HTTPException(400,'存在无效兴趣模块')
        c.execute(user_modules.delete().where(user_modules.c.user_id==u['id'])); c.execute(user_modules.insert(),[{'user_id':u['id'],'module_id':i,'created_at':now()} for i in set(x.module_ids)]); c.execute(users.update().where(users.c.id==u['id']).values(interests=jt([r['name'] for r in rs]),onboarding_completed=True))
    return {'completed':True,'interests':[r['name'] for r in rs]}
@app.get('/recommendations')
def recommendations(page_size: int = Query(default=30, ge=1, le=100), u=Depends(current)):
    if not u['onboarding_completed']:
        return {'onboarding_required': True, 'items': [], 'metrics': match_summary([])}
    with engine.connect() as c:
        rows = c.execute(select(contents).where(contents.c.status == 'published')).mappings().all()
        history = c.execute(select(events).where(events.c.user_id == u['id'])).mappings().all()
    ranked = rank_contents(u, rows, history)
    return {'onboarding_required': False, 'items': ranked[:page_size],
            'metrics': match_summary(ranked[:page_size]), 'total': len(ranked)}
@app.get('/contents')
def browse_contents(section: Literal['all', 'activities', 'info'] = 'all', q: str = Query('', max_length=200), limit: int = Query(100, ge=1, le=200), u=Depends(current)):
    with engine.connect() as c:
        rows = c.execute(select(contents).where(contents.c.status == 'published').order_by(contents.c.publish_time.desc(), contents.c.id.desc())).mappings().all()
    visible = []
    for row in rows:
        if not content_visible(u, row) or not content_active(row):
            continue
        item = cpub(row)
        activity = item['content_type'] in {'activity', 'competition', 'lecture'}
        if (section == 'activities' and not activity) or (section == 'info' and activity):
            continue
        if q and q.lower() not in (str(item.get('title') or '') + str(item.get('body') or '')).lower():
            continue
        item['content_type_label'] = CONTENT_TYPES[item['content_type']]
        visible.append(item)
    return {'items': visible[:limit], 'total': len(visible)}


@app.get('/contents/{content_id}')
def content_detail(content_id:int,u=Depends(current)):
    """Return the complete article text, metadata and official source link."""
    with engine.connect() as c:
        r=c.execute(select(contents).where(contents.c.id==content_id, contents.c.status=='published')).mappings().first()
    if not r or not content_visible(u, r) or not content_active(r): raise HTTPException(404,'信息不存在或已下线')
    return cpub(r)
@app.post('/events')
def event(x:Event,u=Depends(current)):
    with engine.begin() as c:
        row = c.execute(select(contents).where(contents.c.id == x.content_id, contents.c.status == 'published')).mappings().first()
        if not row or not content_visible(u, row) or not content_active(row):
            raise HTTPException(404, '信息不存在或不可访问')
        c.execute(events.insert().values(user_id=u['id'], content_id=x.content_id, event_type=x.event_type, source=x.source, timestamp=now()))
    return {'status':'recorded'}
@app.post('/activities/{content_id}/register')
def register_activity(content_id:int,u=Depends(current)): event(Event(content_id=content_id,event_type='register'),u); return {'status':'registered'}
def _cache_answer(payload, user_id, version):
    answer_id = uuid.uuid4().hex
    at = datetime.now(timezone.utc)
    with _answer_cache_lock:
        for key in [key for key, entry in _answer_cache.items() if entry[0] <= at]:
            _answer_cache.pop(key)
        _answer_cache[answer_id] = (at + timedelta(hours=24), user_id, payload, version)
        while len(_answer_cache) > 1000:
            _answer_cache.popitem(last=False)
    return answer_id


@app.post('/rag/rebuild')
def rebuild_rag(u=Depends(current)):
    if u.get('role') not in {'admin', 'teacher'}:
        raise HTTPException(403, '无权重建知识库')
    snapshot = _rag_index.get(force=True)
    with _answer_cache_lock:
        _answer_cache.clear()
    return {'documents': len(snapshot.contents), 'chunks': len(snapshot.chunks)}


@app.post('/rag/ask')
def rag(x:Ask, u=Depends(current)):
    snapshot = _rag_index.get()
    sources = _rag_index.search(snapshot, u, x.question, float(os.getenv('RAG_SEMANTIC_MIN_SCORE', '0.30')))
    gate = jev.evidence_sufficient(x.question, sources)
    answer = ('根据校园资料库：\n' + '\n\n'.join(f"[{i}]《{source['title']}》：{source['snippet']}" for i, source in enumerate(sources, 1))) if sources else RAG_REFUSAL
    if gate['status'] == 'insufficient':
        answer = '检索到了相关校园资料，但现有证据不足以可靠回答该问题。请核对原文或联系相关部门。'
    elif gate['status'] == 'uncertain':
        answer = '检索到了可能相关的资料，但证据尚不充分，暂不作出结论。请核对下方原文和适用条件。'
    payload = {'answer': answer, 'sources': sources,
               'grounded': bool(sources) and gate['status'] in {'sufficient', 'unchecked'},
               'model': 'local-hybrid-rrf+jev-gate' if gate['source'] == 'jev' else 'local-hybrid-rrf',
               'evidence': gate, 'evidence_probability': gate['probability']}
    return {**payload, 'answer_id': _cache_answer(payload, u['id'], snapshot.version)}


@app.post('/assistant/ask')
def assistant_ask(x:Ask, u=Depends(current)):
    decision = jev.route_question(x.question)
    route = decision['route']
    if route == 'campus_qa':
        return {'decision': decision, 'target_page': 'campus-qa', 'message': '已查询校园资料。',
                'result': rag(x, u)}
    # Navigation only: routing never authorizes actions or evaluates eligibility.
    target, message = {
        'scholarship': ('ask', '这个问题适合使用教务助手。进入后确认评选年度与考核学年，再开始资格初评。'),
        'academic': ('academic', '可以在学业档案查看和核对自己的成绩及排名信息。'),
        'recommendation': ('home', '可以在推荐首页查看当前可访问的校园活动、竞赛与资讯。'),
        'other': (None, '暂未找到明确的校园服务入口。请补充具体需求，或关闭自动分流后查询校园资料。'),
    }[route]
    return {'decision': decision, 'target_page': target, 'message': message, 'result': None}



@app.get('/rag/sources/{answer_id}')
def rag_sources(answer_id:str, u=Depends(current)):
    with _answer_cache_lock:
        item = _answer_cache.get(answer_id)
        if item and item[0] <= datetime.now(timezone.utc):
            _answer_cache.pop(answer_id, None)
            item = None
    if not item or item[1] != u['id']:
        raise HTTPException(404, '答案来源已过期或不存在')
    snapshot = _rag_index.get()
    if snapshot.version != item[3] or any(
        not (row := snapshot.contents.get(source['content_id'])) or
        not content_visible(u, row) or not content_active(row)
        for source in item[2]['sources']
    ):
        with _answer_cache_lock:
            _answer_cache.pop(answer_id, None)
        raise HTTPException(404, '资料或访问范围已变化，请重新提问')
    return {'answer_id': answer_id, **item[2]}


@app.post('/rag/explain')
def rag_explain(x:Explain, u=Depends(current)):
    with engine.connect() as c:
        rows = c.execute(select(contents).where(contents.c.status == 'published')).mappings().all()
        history = c.execute(select(events).where(events.c.user_id == u['id'])).mappings().all()
    item = next((r for r in rank_contents(u, rows, history) if r['id'] == x.content_id), None)
    if item is None:
        raise HTTPException(404, '内容不存在或已不在可推荐范围')
    source = {'content_id': item['id'], 'title': item['title'], 'snippet': (item.get('body') or '')[:200], **source_details(item)}
    return {'answer': '推荐理由：' + item['reason'], 'score': item['score'],
            'score_detail': item['score_detail'], 'sources': [source], 'grounded': True}
@app.get('/health')
def health(): return {'status':'ok','database':engine.url.get_backend_name()}
