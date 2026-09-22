"""Mocked Jev contracts and failure behavior; no external requests."""
import json
from types import SimpleNamespace

import pytest
from app import jev


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('JEV_ENABLED', 'true')
    monkeypatch.setenv('TYPESAFE_API_KEY', 'test-secret-not-real')
    for name in ['JEV_ROUTER_MIN_CONFIDENCE', 'JEV_EVIDENCE_MIN_PROBABILITY',
                 'JEV_EVIDENCE_ALLOW_PROBABILITY', 'JEV_TIMEOUT_SECONDS']:
        monkeypatch.delenv(name, raising=False)


def choice(route='scholarship', confidence=0.95):
    probabilities = {key: (0.96 if key == route else 0.01) for key in jev.ROUTES}
    return SimpleNamespace(choices={'route': SimpleNamespace(
        choice=route, confidence=confidence, probabilities=probabilities)})


def evidence(probability):
    return SimpleNamespace(nouls={'evidence': SimpleNamespace(noul=probability)})


@pytest.mark.parametrize('flag,key,reason', [('false', 'unused', 'disabled'), ('true', '', 'missing_key')])
def test_no_client_without_configuration(monkeypatch, flag, key, reason):
    monkeypatch.setenv('JEV_ENABLED', flag)
    monkeypatch.setenv('TYPESAFE_API_KEY', key)
    monkeypatch.setattr(jev, '_evaluate', lambda *args: pytest.fail('Must not call Jev'))
    assert jev.route_question('我能申请奖学金吗')['reason'] == reason
    result = jev.evidence_sufficient('需要什么材料', [{'title': '演示'}])
    assert result['reason'] == reason
    assert result['probability'] is None and result['sufficient'] is None


@pytest.mark.parametrize('route', list(jev.ROUTES))
def test_router_closed_set(configured, monkeypatch, route):
    monkeypatch.setattr(jev, '_evaluate', lambda *args: choice(route))
    result = jev.route_question('虚构测试问题')
    assert result['source'] == 'jev' and result['route'] == route


def test_uncertain_route_falls_back(configured, monkeypatch):
    monkeypatch.setattr(jev, '_evaluate', lambda *args: choice(confidence=0.4))
    result = jev.route_question('虚构测试问题')
    assert result['route'] == 'campus_qa' and result['source'] == 'fallback'
    assert result['suggested_route'] == 'scholarship' and result['reason'] == 'low_confidence'


@pytest.mark.parametrize('confidence', [float('nan'), float('inf'), -0.2, 1.1, True, '0.9'])
def test_invalid_router_result_falls_back(configured, monkeypatch, confidence):
    monkeypatch.setattr(jev, '_evaluate', lambda *args: choice(confidence=confidence))
    assert jev.route_question('测试问题')['reason'] == 'service_error'


def test_unknown_route_and_bad_distribution(configured, monkeypatch):
    for change in [{'choice': 'admin_delete'}, {'probabilities': {'campus_qa': 1}},
                   {'probabilities': {key: 1 for key in jev.ROUTES}}]:
        response = choice()
        for key, value in change.items():
            setattr(response.choices['route'], key, value)
        monkeypatch.setattr(jev, '_evaluate', lambda *args: response)
        assert jev.route_question('测试问题')['source'] == 'fallback'


@pytest.mark.parametrize('value,status', [(0, 'insufficient'), (0.54, 'insufficient'),
    (0.55, 'uncertain'), (0.79, 'uncertain'), (0.8, 'sufficient'), (1, 'sufficient')])
def test_evidence_thresholds(configured, monkeypatch, value, status):
    monkeypatch.setattr(jev, '_evaluate', lambda *args: evidence(value))
    result = jev.evidence_sufficient('虚构问题', [{'snippet': '虚构材料'}])
    assert result['status'] == status
    assert result['sufficient'] == (status == 'sufficient')


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, 2, True, '0.9'])
def test_invalid_evidence_never_claims_verified(configured, monkeypatch, value):
    monkeypatch.setattr(jev, '_evaluate', lambda *args: evidence(value))
    result = jev.evidence_sufficient('虚构问题', [{'snippet': '虚构材料'}])
    assert result['status'] == 'unchecked' and result['probability'] is None


def test_empty_sources_do_not_call_model(configured, monkeypatch):
    monkeypatch.setattr(jev, '_evaluate', lambda *args: pytest.fail('Empty evidence must stay local'))
    assert jev.evidence_sufficient('测试问题', [])['status'] == 'no_sources'


def test_data_minimization(configured, monkeypatch):
    captured = []
    def fake(state, questions):
        captured.append(state)
        return evidence(0.9)
    monkeypatch.setattr(jev, '_evaluate', fake)
    sources = [dict(title='示例', snippet='文' * 2000, source_type='manual',
                    verification_status='unverified', password='secret', student_id='private')]*8
    jev.evidence_sufficient('问' * 600, sources)
    state = captured[0]
    assert len(state['sources']) == 5 and len(state['question']) == 500
    assert len(state['sources'][0]['snippet']) == 1000
    assert set(state['sources'][0]) == {'title', 'snippet', 'source_type', 'verification_status'}
    assert 'private' not in json.dumps(state) and 'secret' not in json.dumps(state)


def test_failures_do_not_leak_key_or_question(configured, monkeypatch, caplog):
    def broken(*args):
        raise TimeoutError('test-secret-not-real private-question')
    monkeypatch.setattr(jev, '_evaluate', broken)
    route = jev.route_question('private-question')
    gate = jev.evidence_sufficient('private-question', [{'snippet': 'private-question'}])
    assert route['source'] == gate['source'] == 'fallback'
    output = caplog.text + json.dumps([route, gate])
    assert 'test-secret-not-real' not in output and 'private-question' not in output
    assert 'TimeoutError' in caplog.text


def test_configuration_bounds(monkeypatch):
    for value in ['NaN', 'invalid', '2', '-1']:
        monkeypatch.setenv('JEV_ROUTER_MIN_CONFIDENCE', value)
        assert jev._number('JEV_ROUTER_MIN_CONFIDENCE', 0.7) == 0.7


def test_sdk_configuration_has_bounded_timeout_no_retries(configured, monkeypatch):
    captured = {}
    class Client:
        def __init__(self, **kwargs): captured.update(kwargs)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def system_one(self, **kwargs): return choice()
    monkeypatch.setattr(jev, 'TypeSafeClient', Client)
    assert jev.route_question('虚构测试')['source'] == 'jev'
    assert captured['timeout'] == 12 and captured['retry'].max_retries == 0
