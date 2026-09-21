import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app import campus
from app.access import classes, audit
from app.academic import store
from app.settings import jwt_secret, cors_origins


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def account(client, role='student'):
    name='scope_' + uuid.uuid4().hex[:10]
    result=client.post('/auth/register', json=dict(username=name,password='test-password-123',name='模拟用户',college='信息工程学院',major='计算机科学与技术',grade='大一'))
    assert result.status_code == 200
    identifier=result.json()['user_id']
    if role != 'student':
        with campus.engine.begin() as conn:
            conn.execute(campus.users.update().where(campus.users.c.id==identifier).values(role=role))
    return identifier, {'Authorization': 'Bearer ' + campus.token(identifier)}


def create_class(client, admin, college='information_engineering'):
    name='测试班级-' + uuid.uuid4().hex[:6]
    assert client.post('/admin/classes',headers=admin,json=dict(name=name,college_code=college)).status_code==200
    return name


def test_staff_provisioning_scope_revocation_and_audit(client):
    admin_id, admin=account(client,'admin')
    sid, student=account(client)
    cid, counselor=account(client,'counselor')
    class_a=create_class(client,admin)
    class_b=create_class(client,admin,'energy_engineering')
    assert client.get('/admin/users',headers=student).status_code==403
    assert client.post('/admin/users',headers=counselor,json={}).status_code==403
    assert client.patch(f'/admin/users/{sid}/access',headers=admin,json=dict(role='student',college_code='information_engineering',class_name=class_a)).status_code==200
    access=dict(role='counselor',college_code='information_engineering',managed_classes=[class_a])
    assert client.patch(f'/admin/users/{cid}/access',headers=admin,json=access).status_code==200
    assert sid in {row['id'] for row in client.get('/management/students',headers=counselor).json()}
    assert client.get(f'/management/students/{sid}/profile',headers=counselor).status_code==200
    assert client.get(f'/management/students/{sid}/profile',headers=student).status_code==403
    with campus.engine.begin() as conn:
        ranking_a=store.create(conn,store.rankings,admin_id,{'ranking':{'class_name':class_a},'sheets':[]})
        ranking_b=store.create(conn,store.rankings,admin_id,{'ranking':{'class_name':class_b},'sheets':[]})
    assert client.get('/class-rankings/'+ranking_a['id'],headers=counselor).status_code==200
    assert client.get('/class-rankings/'+ranking_b['id'],headers=counselor).status_code==404
    denied=client.post('/class-rankings',headers=counselor,data=dict(academic_year='2025-2026',class_name=class_b),files=[('files',('1.png',b'x','image/png')),('files',('2.png',b'x','image/png'))])
    assert denied.status_code==403
    access['managed_classes']=[]
    assert client.patch(f'/admin/users/{cid}/access',headers=admin,json=access).status_code==200
    assert client.get('/class-rankings/'+ranking_a['id'],headers=counselor).status_code==404
    assert client.get(f'/management/students/{sid}/profile',headers=counselor).status_code==404
    logs=client.get('/admin/audit',headers=admin).json()
    assert any(row['action']=='read_student_profile' and row['target']==str(sid) for row in logs)
    assert 'password' not in str(logs)
    assert client.patch(f'/admin/users/{admin_id}/access',headers=admin,json=dict(role='student')).status_code==409


def test_college_manager_scope_and_staff_creation(client):
    _,admin=account(client,'admin')
    sid,student=account(client)
    username='staff_'+uuid.uuid4().hex[:10]
    response=client.post('/admin/users',headers=admin,json=dict(username=username,name='模拟院管',password='staff-password-123',role='academic_admin',college_code='energy_engineering'))
    assert response.status_code==200, response.text
    assert 'password_hash' not in response.json()
    manager={'Authorization':'Bearer '+campus.token(response.json()['id'])}
    assert client.get(f'/management/students/{sid}/profile',headers=manager).status_code==404
    assert client.get('/admin/audit',headers=manager).status_code==403
    updated=client.patch(f"/admin/users/{response.json()['id']}/access",headers=admin,json=dict(role='academic_admin',college_code='information_engineering'))
    assert updated.status_code==200
    assert client.get(f'/management/students/{sid}/profile',headers=manager).status_code==200
    assert client.post('/admin/users',headers=admin,json=dict(username=username,name='模拟',password='staff-password-123',role='academic_admin')).status_code==422


def test_identity_cannot_be_overridden_by_self_report_or_stale_profile(client):
    sid, student=account(client)
    assert client.patch('/academic-profile',headers=student,json={'facts':{'grade_level':{'value':4}}}).status_code==422
    with campus.engine.begin() as conn:
        record=store.profile(conn,sid)
        payload=record['payload']
        payload['facts']['college']={'value':'伪造学院','confirmed':True}
        store.save(conn,store.profiles,record,payload)
    profile=client.get('/academic-profile',headers=student).json()['payload']
    assert profile['facts']['college']['value']=='信息工程学院'
    assert profile['facts']['grade_level']['value']==1


def test_strong_secret_and_explicit_cors(monkeypatch,client):
    monkeypatch.delenv('JWT_SECRET',raising=False)
    with pytest.raises(RuntimeError): jwt_secret()
    monkeypatch.setenv('JWT_SECRET','dev-secret')
    with pytest.raises(RuntimeError): jwt_secret()
    monkeypatch.setenv('JWT_SECRET','x'*48)
    assert len(jwt_secret())==48
    monkeypatch.setenv('CORS_ORIGINS','*')
    with pytest.raises(RuntimeError): cors_origins()
    monkeypatch.setenv('CORS_ORIGINS','http://localhost:5173')
    assert cors_origins()==['http://localhost:5173']
    response=client.options('/auth/login',headers={'Origin':'https://untrusted.example','Access-Control-Request-Method':'POST'})
    assert 'access-control-allow-origin' not in response.headers


def test_shared_content_type_catalog(client):
    from app.content_types import normalize_type
    catalog=client.get('/catalog/content-types').json()
    assert {row['code'] for row in catalog}=={'notice','activity','competition','lecture','employment','postgraduate','scholarship','academic'}
    assert normalize_type('teaching')=='academic'
    assert normalize_type('竞赛')=='competition'
    assert normalize_type('club')=='activity'


def test_content_browse_respects_permissions_and_filter(client):
    _,student=account(client)
    with campus.engine.begin() as conn:
        public=conn.execute(campus.contents.insert().values(title='catalog-public-test',body='unique-catalog-query',content_type='competition',status='published',target_roles='["student"]')).inserted_primary_key[0]
        hidden=conn.execute(campus.contents.insert().values(title='catalog-hidden-test',body='unique-catalog-query',content_type='competition',status='published',target_roles='["admin"]')).inserted_primary_key[0]
    result=client.get('/contents?section=activities&q=unique-catalog-query',headers=student).json()
    assert [row['id'] for row in result['items']]==[public]
    assert not client.get('/contents?section=info&q=unique-catalog-query',headers=student).json()['items']
    assert client.get(f'/contents/{hidden}',headers=student).status_code==404


def test_legacy_source_categories_remain_unverified():
    from app.source_metadata import normalize_source
    assert normalize_source({'source_type':'教务处通知'})['source_type']=='unknown'
    assert normalize_source({'source_type':'校园新闻'})['last_verified_at'] is None
