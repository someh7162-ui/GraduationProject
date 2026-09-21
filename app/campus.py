from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, uuid, re, logging, math
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, Boolean, select, inspect, text
# Bound BLAS startup threads for the lightweight campus workload.
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
ROOT=Path(__file__).resolve().parents[1]; STATIC=ROOT/'frontend'
load_dotenv(ROOT / '.env')
logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
logger=logging.getLogger(__name__)
SECRET=os.getenv('JWT_SECRET','dev-secret')
def url():
    if os.getenv('DATABASE_URL'): return os.getenv('DATABASE_URL')
    if os.getenv('MYSQL_PASSWORD') is not None: return f"mysql+pymysql://{os.getenv('MYSQL_USER','root')}:{os.getenv('MYSQL_PASSWORD')}@{os.getenv('MYSQL_HOST','127.0.0.1')}:{os.getenv('MYSQL_PORT','3306')}/{os.getenv('MYSQL_DB','campus_recommender')}?charset=utf8mb4"
    return f"sqlite:///{os.getenv('CAMPUS_DB',ROOT/'campus.db')}"
engine=create_engine(url(),future=True,pool_pre_ping=True); md=MetaData()
users=Table('users',md,Column('id',Integer,primary_key=True),Column('username',String(80),unique=True),Column('name',String(120)),Column('password_hash',String(255)),Column('role',String(30)),Column('college',String(120)),Column('major',String(120)),Column('grade',String(30)),Column('interests',Text,default='[]'),Column('onboarding_completed',Boolean,default=False),Column('is_active',Boolean,default=True),Column('created_at',String(40)))
contents=Table('contents',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('title',String(200)),Column('body',Text),Column('summary',Text),Column('content_type',String(40)),Column('publisher_id',Integer),Column('target_roles',Text,default='[]'),Column('target_colleges',Text,default='[]'),Column('target_majors',Text,default='[]'),Column('target_grades',Text,default='[]'),Column('tags',Text,default='[]'),Column('source_url',String(500)),Column('source_site',String(200)),Column('source_department',String(200)),Column('source_id',String(200)),Column('content_hash',String(64)),Column('crawl_time',String(40)),Column('updated_at',String(40)),Column('start_time',String(40)),Column('end_time',String(40)),Column('publish_time',String(40)),Column('status',String(30),default='published'))
events=Table('user_events',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('user_id',Integer),Column('content_id',Integer),Column('event_type',String(40)),Column('source',String(40)),Column('timestamp',String(40)))
feedbacks=Table('feedbacks',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('user_id',Integer),Column('content_id',Integer),Column('feedback_type',String(40)),Column('reason',Text),Column('created_at',String(40)))
modules=Table('interest_modules',md,Column('id',Integer,primary_key=True,autoincrement=True),Column('name',String(80),unique=True),Column('description',String(255)),Column('icon',String(20)),Column('recommended_grades',Text),Column('recommended_roles',Text),Column('sort_order',Integer))
user_modules=Table('user_interests',md,Column('user_id',Integer,primary_key=True),Column('module_id',Integer,primary_key=True),Column('created_at',String(40)))
app=FastAPI(title='校园信息推荐系统'); app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
def now(): return datetime.now(timezone.utc).isoformat()
def pj(v):
    try: x=json.loads(v or '[]') if isinstance(v,str) else v; return x if isinstance(x,list) else []
    except: return []
def jt(v): return json.dumps(v or [],ensure_ascii=False)
def hp(v):
    s=secrets.token_bytes(16); d=hashlib.pbkdf2_hmac('sha256',v.encode(),s,180000); return 'p$'+base64.urlsafe_b64encode(s).decode()+'$'+base64.urlsafe_b64encode(d).decode()
def vp(v,e):
    try: _,s,d=e.split('$'); return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',v.encode(),base64.urlsafe_b64decode(s),180000),base64.urlsafe_b64decode(d))
    except: return False
def token(i): return jwt.encode({'sub':str(i),'exp':datetime.now(timezone.utc)+timedelta(hours=24)},SECRET,algorithm='HS256')
def pub(r):
    d=dict(r); d['interests']=pj(d.get('interests')); d.pop('password_hash',None); return d
def cpub(r):
    d=dict(r)
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
            for name, ddl in {'username':'VARCHAR(80)','password_hash':'VARCHAR(255)','onboarding_completed':'BOOLEAN DEFAULT 0','is_active':'BOOLEAN DEFAULT 1'}.items():
                if name not in cols: c.execute(text(f'ALTER TABLE users ADD COLUMN {name} {ddl}'))
        if inspect(c).has_table('contents'):
            cols={x['name'] for x in inspect(c).get_columns('contents')}
            additions={'target_grades':'TEXT','summary':'TEXT','target_majors':'TEXT','source_url':'VARCHAR(500)','source_site':'VARCHAR(200)','source_department':'VARCHAR(200)','source_id':'VARCHAR(200)','content_hash':'VARCHAR(64)','crawl_time':'VARCHAR(40)','updated_at':'VARCHAR(40)'}
            for name,ddl in additions.items():
                if name not in cols: c.execute(text(f'ALTER TABLE contents ADD COLUMN {name} {ddl}'))
        if c.execute(select(modules.c.id)).first() is None: c.execute(modules.insert(),[{'name':n,'description':f'{n}相关校园信息','icon':'✦','recommended_grades':jt(['大一'] if n=='新生入学' else (['大四'] if n in ['就业实习','考研升学'] else [])),'recommended_roles':jt(['counselor'] if n=='班级管理' else (['organizer'] if n=='活动运营' else ['student'])),'sort_order':i} for i,n in enumerate(SEEDS)])
        _ensure_unique_hash(c)
        if c.execute(select(users.c.id).limit(1)).first() is None:
            c.execute(users.insert(),[{'username':'legacy_admin','name':'历史管理员','password_hash':None,'role':'admin','college':'','major':'','grade':'','interests':'[]','onboarding_completed':False,'is_active':False,'created_at':now()}])
            p=c.execute(select(users.c.id)).scalar_one(); data=[('新生入学报到指南','大一新生报到流程、校园卡领取、宿舍入住和军训安排。','notice',['student'],['大一'],['新生入学','校园生活']),('大四就业与实习双选会','面向大四学生的秋季就业双选会，提供简历诊断和现场面试。','activity',['student'],['大四'],['就业实习','就业']),('校园创新创业讲座','分享项目孵化、商业计划书和竞赛经验。','lecture',['student'],[],['创新创业']),('奖学金申请通知','本年度奖学金申请开始，请提交申请材料。','notice',['student'],[],['奖助学金']),('校园志愿服务招募','招募志愿者参与校园志愿服务。','activity',['student'],[],['志愿服务'])]
            c.execute(contents.insert(),[{'title':t,'body':b,'summary':b[:160],'content_type':typ,'publisher_id':p,'target_roles':jt(r),'target_colleges':'[]','target_majors':'[]','target_grades':jt(g),'tags':jt(tags),'publish_time':now(),'end_time':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat(),'status':'published'} for t,b,typ,r,g,tags in data])
init_db()
class Reg(BaseModel): username:str=Field(min_length=3,max_length=40,pattern=r'^[A-Za-z0-9_]+$'); password:str=Field(min_length=8); name:str; role:str; college:str=''; major:str=''; grade:str=''
class Login(BaseModel): username:str; password:str
class Interests(BaseModel): module_ids:list[int]=Field(min_length=3,max_length=8)
class Event(BaseModel): content_id:int; event_type:str; source:str='homepage'
class Ask(BaseModel): question:str=Field(min_length=2,max_length=500)
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
    if x.role not in ['student','counselor','organizer']: raise HTTPException(422,'角色不合法')
    if x.role=='student' and not x.grade: raise HTTPException(422,'学生必须填写年级')
    with engine.begin() as c:
        if c.execute(select(users.c.id).where(users.c.username==x.username)).first(): raise HTTPException(409,'用户名已存在')
        i=c.execute(users.insert().values(username=x.username,name=x.name,password_hash=hp(x.password),role=x.role,college=x.college,major=x.major,grade=x.grade,interests='[]',onboarding_completed=False,is_active=True,created_at=now())).inserted_primary_key[0]
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
def recommendations(u=Depends(current)):
    if not u['onboarding_completed']: return {'onboarding_required':True,'items':[]}
    with engine.connect() as c: rs=c.execute(select(contents).where(contents.c.status=='published')).mappings().all(); evs=c.execute(select(events).where(events.c.user_id==u['id'])).mappings().all()
    interests=set(pj(u['interests'])); out=[]
    # Behaviour profile built once from the *actual* content the user interacted with.
    # A dismiss on content X must penalise X's tags only, never the current candidate's tags.
    tags_by_id={r['id']:set(pj(r['tags'])) for r in rs}
    positive=set(); negative=set()
    for e in evs:
        et=e['event_type']; etags=tags_by_id.get(e['content_id']) or set()
        if et=='dismiss': negative.update(etags)
        elif et in ('favorite','register','share','click','view'): positive.update(etags)
    for r in rs:
        roles,grades,tags,colleges,majors=pj(r['target_roles']),pj(r['target_grades']),pj(r['tags']),pj(r.get('target_colleges')),pj(r.get('target_majors'))
        if (roles and u['role'] not in roles) or (grades and u['grade'] not in grades) or (colleges and u.get('college') not in colleges) or (majors and u.get('major') not in majors): continue
        status,days,urg=deadline_info(r.get('end_time'))
        if status=='expired': continue
        content_score=len(interests&set(tags))/max(1,len(interests)); profile_score=len(positive&set(tags))/max(1,len(positive)) if positive else 0
        if negative&set(tags): profile_score-=0.3
        freshness=1.0
        pd=parse_dt(r.get('publish_time'))
        if pd: freshness=max(0.0,1-(datetime.now(timezone.utc)-pd).days/365)
        score=max(0.0,0.55*content_score+0.2*profile_score+0.15*freshness+0.1*urg)
        d=cpub(r); matched=list((interests|positive)&set(tags)); reason='与你关注的'+('、'.join(matched) if matched else '校园信息')+'相关'; d.update(score=round(score,4),reason=reason,matched_tags=matched,score_detail={'content':round(content_score,3),'profile':round(profile_score,3),'freshness':round(freshness,3),'urgency':urg},deadline=r.get('end_time'),deadline_status=status,days_remaining=days); out.append(d)
    return {'onboarding_required':False,'items':sorted(out,key=lambda x:x['score'],reverse=True)}
@app.get('/contents/{content_id}')
def content_detail(content_id:int,u=Depends(current)):
    """Return the complete article text, metadata and official source link."""
    with engine.connect() as c:
        r=c.execute(select(contents).where(contents.c.id==content_id, contents.c.status=='published')).mappings().first()
    if not r: raise HTTPException(404,'信息不存在或已下线')
    return cpub(r)
@app.post('/events')
def event(x:Event,u=Depends(current)):
    with engine.begin() as c:c.execute(events.insert().values(user_id=u['id'],content_id=x.content_id,event_type=x.event_type,source=x.source,timestamp=now()))
    return {'status':'recorded'}
@app.post('/activities/{content_id}/register')
def register_activity(content_id:int,u=Depends(current)): event(Event(content_id=content_id,event_type='register'),u); return {'status':'registered'}
@app.post('/rag/ask')
def rag(x:Ask,u=Depends(current)):
    with engine.connect() as c:rs=c.execute(select(contents).where(contents.c.status=='published')).mappings().all()
    if not rs:return {'answer':'当前校园资料库中暂无可靠信息。','sources':[]}
    docs=[f"{r['title']} {r.get('summary') or ''} {r['body']} {' '.join(pj(r.get('tags')))}" for r in rs]
    try:
        vec=TfidfVectorizer(analyzer='char',ngram_range=(2,4),min_df=1); mat=vec.fit_transform(docs); sims=cosine_similarity(vec.transform([x.question]),mat)[0]
    except Exception as ex: logger.warning('RAG vectorization failed: %s',ex); sims=[0]*len(rs)
    order=sorted(range(len(rs)),key=lambda i:sims[i],reverse=True); ranked=[rs[i] for i in order[:5]]; scores=[float(sims[i]) for i in order[:5]]
    if not ranked or max(scores,default=0)<float(os.getenv('RAG_MIN_SCORE','0.02')): return {'answer':'当前校园资料库中暂无可靠信息。','sources':[],'model':'local-retrieval'}
    snippets=[]
    for r in ranked[:3]:
        body=(r.get('body') or r.get('summary') or '').strip()
        snippets.append(f"《{r['title']}》：{body[:700]}")
    local='根据校园资料库：\n'+'\n\n'.join(snippets)
    answer=local; model='local-retrieval'
    if os.getenv('DEEPSEEK_API_KEY'):
        context='\n'.join(f"{r['title']}：{r['body']}" for r in ranked)
        payload=json.dumps({'model':os.getenv('DEEPSEEK_MODEL','deepseek-chat'),'temperature':0.1,'messages':[{'role':'system','content':'你是校园信息助手，只能依据提供的校园资料回答，资料不足时明确说明。'},{'role':'user','content':f'问题：{x.question}\n资料：{context}'}]}).encode()
        req=urllib.request.Request(os.getenv('DEEPSEEK_BASE_URL','https://api.deepseek.com').rstrip('/')+'/chat/completions',data=payload,headers={'Authorization':'Bearer '+os.getenv('DEEPSEEK_API_KEY'),'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=15) as resp: answer=json.loads(resp.read().decode())['choices'][0]['message']['content']; model=os.getenv('DEEPSEEK_MODEL','deepseek-chat')
        except Exception as ex: logger.warning('DeepSeek RAG call failed: %s',ex)
    return {'answer':answer,'sources':[{'content_id':r['id'],'title':r['title'],'source_department':r.get('source_department'),'source_url':r.get('source_url'),'similarity_score':round(scores[i],4)} for i,r in enumerate(ranked)],'model':model}
@app.get('/health')
def health(): return {'status':'ok','database':engine.url.get_backend_name()}
