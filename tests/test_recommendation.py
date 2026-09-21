from datetime import datetime, timedelta, timezone
import math
import pytest
from app.recommendation import rank_contents, match_summary
from scripts.evaluate_recommendations import evaluate, metrics_at_k

AT = datetime(2026, 9, 21, tzinfo=timezone.utc)
USER = dict(id=42, role="student", college="信息工程学院", college_code="information_engineering",
            major="计算机科学与技术", major_code="080901", grade="大一", interests=["竞赛"])


def article(identifier, tags=None, **kwargs):
    return dict(id=identifier, tags=tags or ["竞赛"], status="published", publish_time=AT.isoformat(), **kwargs)


def event(identifier, kind, days=0, user_id=42):
    return dict(user_id=user_id, content_id=identifier, event_type=kind, timestamp=(AT-timedelta(days=days)).isoformat())


def score(rows, history):
    return rank_contents(USER, rows, history, at=AT)[0]["score"]


def test_action_strength_duplicates_decay_and_negative_feedback():
    rows = [article(1)]
    baseline = score(rows, [])
    assert score(rows, [event(1, "register")]) > score(rows, [event(1, "favorite")]) > score(rows, [event(1, "click")]) > score(rows, [event(1, "view")]) > baseline
    assert score(rows, [event(1, "click")] * 100) == score(rows, [event(1, "click")])
    assert score(rows, [event(1, "favorite", 30)]) < score(rows, [event(1, "favorite")])
    assert score(rows, [event(1, "dismiss")]) < baseline
    assert score(rows, [event(1, "favorite", -1), event(1, "register", user_id=99)]) == baseline


def test_permissions_time_and_unrelated_negative_feedback():
    rows = [article(1), article(2, ["体育"]), article(3, target_colleges=["其他学院"]),
            article(4, end_time=(AT-timedelta(seconds=1)).isoformat()),
            article(5, target_majors=["080901"]), article(6, target_grades=["大四"])]
    future = article(7); future["publish_time"] = (AT+timedelta(days=1)).isoformat(); rows.append(future)
    hidden_history = [event(3, "register")]
    for strategy in ("interest", "identity", "hybrid"):
        result = rank_contents(USER, rows, hidden_history, at=AT, strategy=strategy)
        assert {r["id"] for r in result} == {1, 2, 5}
    base = {r["id"]: r["score"] for r in rank_contents(USER, rows, [], at=AT)}
    updated = {r["id"]: r["score"] for r in rank_contents(USER, rows, [event(2, "dismiss")], at=AT)}
    assert updated[1] == base[1]
    assert updated[2] < base[2]
    assert score([article(1)], hidden_history) == score([article(1)], [])


def test_metrics_empty_top_ten_and_stable_ties():
    assert match_summary([])["interest_match_rate"] is None
    rows = [{"matched_tags": ["竞赛"] if i < 8 else []} for i in range(12)]
    assert match_summary(rows) == dict(top_k=10, sample_size=10, matched_count=8, interest_match_rate=0.8)
    assert [r["id"] for r in rank_contents(USER, [article(2), article(1)], [], at=AT)] == [1, 2]
    measured = metrics_at_k([1, 2, 3], [1, 3], 3)
    assert measured["precision"] == pytest.approx(2/3)
    assert measured["recall"] == 1
    assert measured["hit_rate"] == 1
    assert measured["ndcg"] == pytest.approx(1.5 / (1 + 1/math.log2(3)))


def test_evaluation_rejects_label_leakage_and_unavailable_labels():
    snapshot = dict(cutoff=AT.isoformat(), contents=[article(1)], cases=[dict(user=USER, history=[event(1, "click")], relevant_ids=[1])])
    with pytest.raises(ValueError, match="before cutoff"):
        evaluate(snapshot)
    snapshot["cases"][0]["history"] = []
    snapshot["cases"][0]["relevant_ids"] = [999]
    with pytest.raises(ValueError, match="eligible"):
        evaluate(snapshot)


def test_cold_start_freshness_deadline_and_score_explanation():
    from app.recommendation import SCORE_WEIGHTS
    old = article(1); old["publish_time"] = (AT-timedelta(days=300)).isoformat()
    recent = article(2)
    urgent = article(3, end_time=(AT+timedelta(hours=12)).isoformat())
    result = rank_contents(USER, [old, recent, urgent], [], at=AT)
    assert [r["id"] for r in result] == [3, 2, 1]
    assert result[0]["deadline_status"] == "today"
    for row in result:
        assert row["score_detail"]["profile"] == 0
        assert row["score"] == pytest.approx(sum(SCORE_WEIGHTS[k]*row["score_detail"][k] for k in SCORE_WEIGHTS), abs=0.0001)
    no_date = article(4); no_date["publish_time"] = None
    assert rank_contents(USER, [no_date], [], at=AT)[0]["score_detail"]["freshness"] == 0


def test_sample_evaluation_is_reproducible_and_labelled_synthetic():
    import json
    from pathlib import Path
    sample = json.loads((Path(__file__).resolve().parents[1] / "data/recommendation_eval_sample.json").read_text(encoding="utf-8"))
    result = evaluate(sample)
    assert result == evaluate(sample)
    assert result["synthetic"] is True
    assert result["users"] == 3
    assert set(result["results"]) == {"interest", "identity", "hybrid"}
    assert result["results"]["interest"]["5"]["precision"] == pytest.approx(7/15, abs=0.000001)
