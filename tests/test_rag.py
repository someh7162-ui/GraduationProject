from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, inspect, text
from app import campus
from app.main import app
from app.rag_index import RagIndex, chunks
from app.source_metadata import normalize_source, source_details
from app.recommendation import rank_contents


@pytest.fixture
def rag_env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'rag.db'}")
    campus.md.create_all(engine)
    index = RagIndex(engine, campus.contents, campus.knowledge_documents, scope_limit=2)
    monkeypatch.setattr(campus, 'engine', engine)
    monkeypatch.setattr(campus, '_rag_index', index)
    user = dict(id=501, role='student', college='信息工程学院', college_code='information_engineering', major='计算机科学与技术', major_code='080901', grade='大一', interests='["奖助学金"]', onboarding_completed=True)
    app.dependency_overrides[campus.current] = lambda: user
    campus._answer_cache.clear()
    def add(**values):
        record = dict(title='星河奖学金申报指南', body='星河奖学金申报需要提交学习成绩单和申请表，请在教务处核对材料。', tags='["奖助学金"]', status='published', source_department='教务处', source_url='https://example.edu/policy', publish_time='2020-01-01T00:00:00+00:00')
        record.update(values)
        with engine.begin() as conn:
            return conn.execute(campus.contents.insert().values(**record)).inserted_primary_key[0]
    with TestClient(app) as client:
        yield client, engine, index, user, add
    app.dependency_overrides.pop(campus.current, None)
    campus._answer_cache.clear()
    engine.dispose()


def ask(client, question='星河奖学金'):
    response = client.post('/rag/ask', json={'question': question})
    assert response.status_code == 200
    return response.json()


def test_tfidf_cache_reuse_and_same_id_edit(rag_env):
    client, engine, index, user, add = rag_env
    identifier = add()
    first = ask(client)
    assert first['grounded'] and index.fit_count == 1
    assert ask(client)['sources'] == first['sources']
    assert index.fit_count == 1 and index.rebuild_count == 1
    with engine.begin() as conn:
        conn.execute(campus.contents.update().where(campus.contents.c.id == identifier).values(body='星河奖学金现在需要提交新版申请材料，交至学生事务中心。'))
    second = ask(client)
    assert '新版' in second['answer']
    assert index.fit_count == 2 and index.rebuild_count == 2
    assert client.get('/rag/sources/' + first['answer_id']).status_code == 404


def test_permissions_on_search_sources_detail_explain_and_events(rag_env):
    client, engine, index, user, add = rag_env
    identifier = add(target_colleges='["information_engineering"]')
    first = ask(client)
    assert first['grounded']
    user['id'] = 502
    assert client.get('/rag/sources/' + first['answer_id']).status_code == 404
    user['id'] = 501
    user['college'] = '其他学院'; user['college_code'] = 'other'
    assert client.get('/rag/sources/' + first['answer_id']).status_code == 404
    assert not ask(client)['grounded']
    assert client.get(f'/contents/{identifier}').status_code == 404
    assert client.post('/rag/explain', json={'content_id': identifier}).status_code == 404
    assert client.post('/events', json={'content_id': identifier, 'event_type': 'click'}).status_code == 404
    assert not client.get('/recommendations').json()['items']


@pytest.mark.parametrize('change', [dict(status='draft'), dict(target_roles='["admin"]'), dict(effective_to='2020-01-01'), dict(effective_from='2099-01-01')])
def test_source_mutations_invalidate_cached_answers(rag_env, change):
    client, engine, index, user, add = rag_env
    identifier = add()
    first = ask(client)
    with engine.begin() as conn:
        conn.execute(campus.contents.update().where(campus.contents.c.id == identifier).values(**change))
    assert client.get('/rag/sources/' + first['answer_id']).status_code == 404
    assert not ask(client)['grounded']
    assert client.post('/rag/explain', json={'content_id': identifier}).status_code == 404


def test_sources_metadata_refusal_rebuild_and_cache_expiry(rag_env):
    client, engine, index, user, add = rag_env
    add(source_type='official_document', source_authority='学生事务中心', last_verified_at='2020-01-02', source_url='javascript:alert(1)')
    result = ask(client)
    source = result['sources'][0]
    assert source['source_department'] == '教务处'
    assert source['source_authority'] == '学生事务中心'
    assert source['verification_status'] == 'recorded'
    assert source['source_url'] is None
    assert client.get('/rag/sources/' + result['answer_id']).status_code == 200
    assert ask(client, 'zxqvbnmlkjh')['sources'] == []
    assert client.post('/rag/rebuild').status_code == 403
    user['role'] = 'admin'
    assert client.post('/rag/rebuild').status_code == 200
    assert client.get('/rag/sources/' + result['answer_id']).status_code == 404
    result = ask(client)
    entry = campus._answer_cache[result['answer_id']]
    campus._answer_cache[result['answer_id']] = (datetime.now(timezone.utc)-timedelta(seconds=1), *entry[1:])
    assert client.get('/rag/sources/' + result['answer_id']).status_code == 404
    assert result['answer_id'] not in campus._answer_cache


def test_concurrent_queries_fit_once_and_scope_cache_is_bounded(rag_env):
    client, engine, index, user, add = rag_env
    add()
    add(target_grades='["大二"]')
    add(target_grades='["大三"]')
    snapshot = index.get()
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: index.search(snapshot, user, '星河奖学金'), range(8)))
    assert all(len(result) == 1 for result in responses)
    assert index.fit_count == 1
    index.search(snapshot, {**user, 'grade': '大二'}, '星河奖学金')
    index.search(snapshot, {**user, 'grade': '大三'}, '星河奖学金')
    assert len(snapshot.scopes) == 2
    assert index.fit_count == 3


def test_metadata_only_import_and_permission_update(rag_env, monkeypatch):
    from scripts import import_campus_data as importer
    client, engine, index, user, add = rag_env
    monkeypatch.setattr(importer, 'engine', engine)
    row = dict(source_id='rag-import', title='星河奖学金', body='星河奖学金申请通知正文。', source_department='教务处')
    assert importer.import_records([row])['added'] == 1
    first = ask(client)
    assert first['sources'][0]['verification_status'] == 'unverified'
    assert importer.import_records([dict(source_id='rag-import', source_type='official_document', last_verified_at='2020-02-02')])['updated'] == 1
    assert client.get('/rag/sources/' + first['answer_id']).status_code == 404
    second = ask(client)
    assert second['sources'][0]['verification_status'] == 'recorded'
    assert importer.import_records([dict(source_id='rag-import', target_roles=['admin'])])['updated'] == 1
    assert not ask(client)['grounded']
    assert importer.import_records([dict(source_id='rag-import', target_roles=['admin'])])['duplicate'] == 1
    assert importer.import_records([dict(source_id='rag-import', last_verified_at='bad-date')])['failed'] == 1
    with engine.connect() as conn:
        record = conn.execute(select(campus.contents)).mappings().one()
    assert record['last_verified_at'].startswith('2020-02-02')
    assert record['target_roles'] == '["admin"]'


def test_empty_text_does_not_rebuild_forever_and_chunk_boundary(rag_env):
    client, engine, index, user, add = rag_env
    add(body='', summary='')
    assert not ask(client)['grounded']
    ask(client)
    assert index.rebuild_count == 1
    result = chunks('短段落。\n\n' + '长' * 800)
    assert result.count('短段落。') == 1
    assert all(0 < len(part) <= 360 for part in result)


def test_validity_expiry_without_database_change(rag_env, monkeypatch):
    client, engine, index, user, add = rag_env
    add(effective_to='2099-01-01')
    result = ask(client)
    from app.source_metadata import content_active
    monkeypatch.setattr(campus, 'content_active', lambda row: content_active(row, datetime(2100, 1, 1, tzinfo=timezone.utc)))
    assert client.get('/rag/sources/' + result['answer_id']).status_code == 404


def test_provenance_validation_does_not_infer_verification():
    assert normalize_source({})['last_verified_at'] is None
    assert source_details({'source_type': 'official_website'})['verification_status'] == 'unverified'
    with pytest.raises(ValueError):
        normalize_source({'effective_from': '2027-01-01', 'effective_to': '2026-01-01'})
    with pytest.raises(ValueError):
        normalize_source({'last_verified_at': '2099-01-01'})
    assert normalize_source({'effective_to': '2026-01-01'})['effective_to'].startswith('2026-01-01T23:59:59')


def test_existing_database_migration_preserves_content(rag_env):
    client, engine, index, user, add = rag_env
    from app.source_metadata import SOURCE_FIELDS
    identifier = add()
    with engine.begin() as conn:
        for name in SOURCE_FIELDS:
            conn.execute(text(f'ALTER TABLE contents DROP COLUMN {name}'))
    campus.init_db()
    campus.init_db()  # Re-running startup migration must remain safe.
    with engine.connect() as conn:
        columns = {column['name'] for column in inspect(conn).get_columns('contents')}
        row = conn.execute(select(campus.contents).where(campus.contents.c.id == identifier)).mappings().one()
    assert set(SOURCE_FIELDS).issubset(columns)
    assert row['title'] == '星河奖学金申报指南'
    assert row['last_verified_at'] is None
    assert ask(client)['sources'][0]['verification_status'] == 'unverified'


def test_explanation_matches_actual_ranking_and_deletion_revokes_sources(rag_env):
    client, engine, index, user, add = rag_env
    identifier = add()
    feed = client.get('/recommendations').json()['items'][0]
    explanation = client.post('/rag/explain', json={'content_id': identifier}).json()
    assert explanation['score'] == feed['score']
    assert explanation['score_detail'] == feed['score_detail']
    result = ask(client)
    with engine.begin() as conn:
        conn.execute(campus.contents.delete().where(campus.contents.c.id == identifier))
    assert client.get('/rag/sources/' + result['answer_id']).status_code == 404
    assert not ask(client)['grounded']


@pytest.mark.parametrize('probability,status,grounded', [(0.2,'insufficient',False),(0.65,'uncertain',False),(0.95,'sufficient',True)])
def test_jev_gate_preserves_sources_and_cache(rag_env, monkeypatch, probability, status, grounded):
    from app import jev
    from types import SimpleNamespace
    client, engine, index, user, add = rag_env
    add()
    monkeypatch.setenv('JEV_ENABLED', 'true')
    monkeypatch.setenv('TYPESAFE_API_KEY', 'mock-key')
    monkeypatch.setattr(jev, '_evaluate', lambda *args: SimpleNamespace(nouls={
        'evidence': SimpleNamespace(noul=probability)}))
    result = ask(client)
    assert result['grounded'] is grounded
    assert result['evidence']['status'] == status
    assert result['sources'] and result['evidence_probability'] == probability
    assert client.get('/rag/sources/' + result['answer_id']).json()['evidence'] == result['evidence']
    if not grounded:
        assert '根据校园资料库' not in result['answer']


def test_jev_receives_only_authorized_sources(rag_env, monkeypatch):
    from app import jev
    from types import SimpleNamespace
    client, engine, index, user, add = rag_env
    add(title='星河奖学金公开申请指南')
    add(title='星河奖学金内部名单', body='INTERNAL_PRIVATE_DATA', target_roles='["admin"]')
    monkeypatch.setenv('JEV_ENABLED', 'true')
    monkeypatch.setenv('TYPESAFE_API_KEY', 'mock-key')
    captured = []
    def fake(state, questions):
        captured.append(state)
        return SimpleNamespace(nouls={'evidence': SimpleNamespace(noul=0.95)})
    monkeypatch.setattr(jev, '_evaluate', fake)
    result = ask(client)
    assert result['grounded'] and len(captured) == 1
    assert 'INTERNAL_PRIVATE_DATA' not in str(captured)
    assert '内部名单' not in str(captured)
    assert set(captured[0]) == {'question', 'sources'}
    assert len(captured[0]['sources']) == 1


@pytest.mark.parametrize('route,target', [('scholarship','ask'),('academic','academic'),('recommendation','home'),('other',None)])
def test_jev_navigation_never_runs_assessment(rag_env, monkeypatch, route, target):
    from app import jev
    client, engine, index, user, add = rag_env
    monkeypatch.setattr(jev, 'route_question', lambda question: {
        'route':route,'confidence':0.9,'source':'jev','probabilities':{},'reason':None})
    monkeypatch.setattr(campus, 'rag', lambda *args: pytest.fail('Navigation must not run RAG'))
    result = client.post('/assistant/ask', json={'question':'模拟问题'}).json()
    assert result['target_page'] == target and result['result'] is None
    assert 'assessment_id' not in result


def test_unified_ask_fallback_and_failed_gate(rag_env, monkeypatch):
    from app import jev
    client, engine, index, user, add = rag_env
    add()
    monkeypatch.setenv('JEV_ENABLED', 'true')
    monkeypatch.setenv('TYPESAFE_API_KEY', 'mock-key')
    def offline(*args): raise TimeoutError('private exception body')
    monkeypatch.setattr(jev, '_evaluate', offline)
    result = client.post('/assistant/ask', json={'question':'星河奖学金'}).json()
    assert result['decision']['source'] == 'fallback'
    assert result['result']['sources'] and result['result']['grounded']
    assert result['result']['evidence']['status'] == 'unchecked'
    assert result['result']['evidence_probability'] is None
    assert 'private exception body' not in str(result)


def test_unified_ask_requires_login_and_valid_input(rag_env):
    client, engine, index, user, add = rag_env
    assert client.post('/assistant/ask', json={'question':'x'}).status_code == 422
    app.dependency_overrides.pop(campus.current)
    assert client.post('/assistant/ask', json={'question':'模拟问题'}).status_code == 401
