"""Tests for CF-native workflow tools: trigger_replenishment_adjustment
and send_classification_notification.

These tools call N8nClient directly on CF (JOULE_RUNTIME unset).
Tests patch tools._get_n8n_client() to return a FakeN8nClient.
"""
import os
import pytest

os.environ.setdefault("IBD_TESTING", "true")
# Ensure JOULE_RUNTIME is unset so CF code path is exercised
os.environ.pop("JOULE_RUNTIME", None)

from tests._helpers import make_fake_n8n


def _invoke_trigger(run_id: str, classifications: list, monkeypatch) -> dict:
    import tools
    fake = make_fake_n8n({"/replenishment": {"run_id": run_id, "processed_count": len(classifications), "status": "completed"}})
    monkeypatch.setattr(tools, "_n8n_client", fake)
    return tools.trigger_replenishment_adjustment.invoke(
        {"run_id": run_id, "classifications": classifications}
    )


def _invoke_notify(monkeypatch, **kwargs) -> dict:
    import tools
    fake = make_fake_n8n({"/classification-notification": {"run_id": kwargs["run_id"], "notified_count": 4, "status": "completed"}})
    monkeypatch.setattr(tools, "_n8n_client", fake)
    return tools.send_classification_notification.invoke(kwargs)


# ── trigger_replenishment_adjustment ────────────────────────────────────────

def test_trigger_replenishment_skips_low_confidence(monkeypatch):
    """Articles with confidence < 60 must not be forwarded."""
    import tools
    fake = make_fake_n8n()
    monkeypatch.setattr(tools, "_n8n_client", fake)
    result = tools.trigger_replenishment_adjustment.invoke({
        "run_id": "r1",
        "classifications": [
            {"article_id": "A1", "classification": "SEASONAL", "confidence_score": 55},
        ],
    })
    assert result["status"] == "skipped_no_eligible_articles"
    assert fake.calls == []  # nothing posted


def test_trigger_replenishment_skips_non_seasonal(monkeypatch):
    """NON_SEASONAL articles must not be forwarded."""
    import tools
    fake = make_fake_n8n()
    monkeypatch.setattr(tools, "_n8n_client", fake)
    result = tools.trigger_replenishment_adjustment.invoke({
        "run_id": "r1",
        "classifications": [
            {"article_id": "A1", "classification": "NON_SEASONAL", "confidence_score": 90},
        ],
    })
    assert result["status"] == "skipped_no_eligible_articles"


def test_trigger_replenishment_posts_eligible(monkeypatch):
    """High-confidence SEASONAL articles are posted to the webhook."""
    result = _invoke_trigger(
        "r2",
        [
            {"article_id": "A1", "classification": "SEASONAL", "confidence_score": 80},
            {"article_id": "A2", "classification": "SEASONAL", "confidence_score": 75},
        ],
        monkeypatch,
    )
    assert result["run_id"] == "r2"
    assert result["processed_count"] == 2


def test_trigger_replenishment_run_id_in_body(monkeypatch):
    """The run_id must appear in the POST body."""
    import tools
    fake = make_fake_n8n({"/replenishment": {"processed_count": 1, "status": "completed"}})
    monkeypatch.setattr(tools, "_n8n_client", fake)
    tools.trigger_replenishment_adjustment.invoke({
        "run_id": "run-xyz",
        "classifications": [{"article_id": "A1", "classification": "SEASONAL", "confidence_score": 85}],
    })
    assert fake.calls[0].body["run_id"] == "run-xyz"


# ── send_classification_notification ─────────────────────────────────────────

def test_send_notification_posts_summary(monkeypatch):
    result = _invoke_notify(
        monkeypatch,
        run_id="r3",
        total_classified=100,
        seasonal_count=30,
        low_confidence_count=5,
        dashboard_url="https://dashboard.example.com",
    )
    assert result["run_id"] == "r3"
    assert result["notified_count"] == 4


def test_send_notification_includes_seasonal_count(monkeypatch):
    import tools
    fake = make_fake_n8n({"/classification-notification": {"run_id": "r4", "notified_count": 4, "status": "completed"}})
    monkeypatch.setattr(tools, "_n8n_client", fake)
    tools.send_classification_notification.invoke({
        "run_id": "r4",
        "total_classified": 200,
        "seasonal_count": 60,
        "low_confidence_count": 10,
        "dashboard_url": "https://dash.example.com",
    })
    body = fake.calls[0].body
    assert body["seasonal_count"] == 60
    assert body["total_classified"] == 200


def test_send_notification_top_articles_optional(monkeypatch):
    """send_classification_notification works without top_seasonal_articles."""
    result = _invoke_notify(
        monkeypatch,
        run_id="r5",
        total_classified=50,
        seasonal_count=10,
        low_confidence_count=2,
        dashboard_url="",
    )
    assert "notified_count" in result or "run_id" in result
