"""Test helpers: FakeN8nClient and related utilities for CF-mode tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FakeCall:
    """Records a single call made through FakeN8nClient."""
    destination_name: str
    path: str
    body: dict[str, Any]
    user_identity: str | None = None


@dataclass
class FakeN8nClient:
    """In-memory fake for N8nClient.

    responses: mapping of path-fragment → payload (or callable returning payload).
    calls:     populated by each .post() invocation for assertion.

    Usage:
        fake = FakeN8nClient(responses={"/replenishment": {"processed_count": 3, "status": "completed"}})
        monkeypatch in test, then assert fake.calls[0].body
    """
    responses: dict[str, Any] = field(default_factory=dict)
    calls: list[FakeCall] = field(default_factory=list)

    def _resolve(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        for needle, payload in self.responses.items():
            if needle in path:
                if callable(payload):
                    return payload(path, body)
                return dict(payload) if isinstance(payload, dict) else payload
        return {"status": "ok", "processed_count": 0}

    async def post(
        self,
        destination_name: str,
        path: str,
        body: dict[str, Any],
        user_identity: str | None = None,
    ) -> dict[str, Any]:
        call = FakeCall(destination_name, path, body, user_identity)
        self.calls.append(call)
        return self._resolve(path, body)

    async def post_replenishment_adjustment(
        self,
        run_id: str,
        classifications: list[dict[str, Any]],
        user_identity: str | None = None,
    ) -> dict[str, Any]:
        body = {"run_id": run_id, "classifications": classifications}
        return await self.post("REPLENISHMENT_WORKFLOW", "/replenishment-adjustment-received", body, user_identity)

    async def post_classification_notification(
        self,
        run_id: str,
        run_date: str,
        total_classified: int,
        seasonal_count: int,
        low_confidence_count: int,
        dashboard_url: str,
        top_seasonal_articles: list[dict[str, Any]] | None = None,
        user_identity: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "run_id": run_id,
            "run_date": run_date,
            "total_classified": total_classified,
            "seasonal_count": seasonal_count,
            "low_confidence_count": low_confidence_count,
            "dashboard_url": dashboard_url,
            "top_seasonal_articles": top_seasonal_articles or [],
        }
        return await self.post(
            "CLASSIFICATION_NOTIFICATION_WORKFLOW",
            "/classification-notification-received",
            body,
            user_identity,
        )


def make_fake_n8n(responses: dict[str, Any] | None = None) -> FakeN8nClient:
    """Convenience factory."""
    return FakeN8nClient(responses=dict(responses or {}))
