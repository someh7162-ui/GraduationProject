"""Core API tests: auth, onboarding, targeting and RAG.

Each test run uses the isolated database created in conftest.py.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

PASSWORD = "password123"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def register(client, username="student_test", role="student", college="计算机学院",
             major="软件工程", grade="大一"):
    return client.post("/auth/register", json={
        "username": username, "password": PASSWORD, "name": "测试用户",
        "role": role, "college": college, "major": major, "grade": grade,
    })


def auth(client, username="student_test"):
    r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def onb(client, headers, module_ids):
    return client.post("/onboarding/interests", headers=headers,
                       json={"module_ids": module_ids})


def test_health_and_registration(client):
    assert client.get("/health").json()["status"] == "ok"
    assert register(client).status_code in {200, 409}
    assert client.post("/auth/login", json={"username": "student_test",
                                            "password": PASSWORD}).status_code == 200


def test_onboarding_required_then_recommendations(client):
    h = auth(client)
    r = client.get("/recommendations", headers=h)
    assert r.status_code == 200
    if r.json().get("onboarding_required"):
        # too few modules -> validation error (422)
        assert client.post("/onboarding/interests", headers=h,
                           json={"module_ids": [1, 2]}).status_code == 422
        assert onb(client, h, [1, 2, 3]).status_code == 200
    assert client.get("/recommendations", headers=h).json()["items"]


def test_grade_targeting_and_rag(client):
    """A 大四 senior must not be offered the 大一-targeted seed item, and RAG works."""
    u = "senior_test"
    assert register(client, username=u, grade="大四").status_code in {200, 409}
    h = auth(client, u)
    # modules: 9=就业实习, 10=考研升学, 6=创新创业 (list is 1-indexed in the DB)
    assert onb(client, h, [9, 10, 6]).status_code == 200
    items = client.get("/recommendations", headers=h).json()["items"]
    assert items
    assert all("新生入学报到指南" not in it["title"] for it in items)
    assert client.post("/rag/ask", headers=h, json={"question": "就业实习"}).status_code == 200


def test_content_target_fields_are_json_arrays(client):
    """The public content payload must not leak serialized target fields."""
    h = auth(client)
    items = client.get("/recommendations", headers=h).json()["items"]
    assert items
    assert all(isinstance(item["target_majors"], list) for item in items)
