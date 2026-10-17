"""n8n workflow webhook client backed by BTP destinations.

Shared client for both workflow webhooks:
  - REPLENISHMENT_WORKFLOW  → POST replenishment adjustment classifications
  - CLASSIFICATION_NOTIFICATION_WORKFLOW → POST notification run summary

Each webhook is reached via its own BTP destination (Internet proxy type —
n8n is BTP-hosted, no Cloud Connector needed).

Required CF service binding:
  destination  — exposes the destination-configuration REST API; its embedded
                 OAuth client (clientid, clientsecret, url) is used to fetch
                 access tokens via client_credentials — no separate xsuaa binding.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Destination names resolved from env vars (set in manifest.yml)
REPLENISHMENT_DESTINATION_NAME = os.environ.get(
    "REPLENISHMENT_WORKFLOW_DESTINATION_NAME", "REPLENISHMENT_WORKFLOW"
)
NOTIFICATION_DESTINATION_NAME = os.environ.get(
    "CLASSIFICATION_NOTIFICATION_WORKFLOW_DESTINATION_NAME",
    "CLASSIFICATION_NOTIFICATION_WORKFLOW",
)

DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("N8N_TIMEOUT_SECONDS", "30.0"))
TOKEN_TTL = float(os.environ.get("DESTINATION_TOKEN_TTL", "600"))
DEST_CACHE_TTL = float(os.environ.get("DESTINATION_CACHE_TTL", "300"))

RESPONSE_ENVELOPE = "rest"
CSRF_REQUIRED = False  # n8n webhooks are plain REST — no CSRF token


def _vcap() -> dict[str, Any]:
    raw = os.environ.get("VCAP_SERVICES")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        logger.warning("VCAP_SERVICES is set but not valid JSON")
        return {}


def _first_binding(label: str) -> dict[str, Any] | None:
    bindings = _vcap().get(label) or []
    if not bindings:
        return None
    return (bindings[0] or {}).get("credentials") or {}


@dataclass
class Destination:
    url: str
    auth_type: str
    username: str | None = None
    password: str | None = None
    additional: dict[str, str] = field(default_factory=dict)


@dataclass
class _CachedToken:
    value: str
    expires_at: float

    def expired(self) -> bool:
        return time.monotonic() >= self.expires_at


class _DestinationResolver:
    def __init__(self, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._token: _CachedToken | None = None
        self._dest_cache: dict[str, tuple[Destination, float]] = {}

    async def _client_credentials_token(
        self, token_url: str, client_id: str, client_secret: str
    ) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                token_url.rstrip("/") + "/oauth/token",
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
        r.raise_for_status()
        return r.json()["access_token"]

    async def _access_token(self) -> str:
        if self._token and not self._token.expired():
            return self._token.value
        creds = _first_binding("destination") or {}
        if not creds:
            raise RuntimeError(
                "No 'destination' service binding found in VCAP_SERVICES. "
                "Bind a destination service instance to the app."
            )
        token = await self._client_credentials_token(
            creds["url"], creds["clientid"], creds["clientsecret"]
        )
        self._token = _CachedToken(token, time.monotonic() + TOKEN_TTL)
        return token

    async def access_token(self) -> str:
        """Public wrapper — returns the destination service access token."""
        return await self._access_token()

    async def resolve(self, name: str) -> Destination:
        cached = self._dest_cache.get(name)
        if cached and time.monotonic() < cached[1]:
            return cached[0]

        creds = _first_binding("destination") or {}
        if not creds:
            raise RuntimeError("No 'destination' service binding found in VCAP_SERVICES.")
        access_token = await self._access_token()
        uri = creds["uri"].rstrip("/")
        url = f"{uri}/destination-configuration/v1/destinations/{name}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
        if r.status_code >= 400:
            raise RuntimeError(
                f"Destination service returned {r.status_code} for '{name}': {r.text}"
            )
        body = r.json()
        cfg = body.get("destinationConfiguration") or {}
        d_url = (cfg.get("URL") or "").rstrip("/")
        if not d_url:
            raise RuntimeError(f"Destination '{name}' has no URL configured.")
        well_known = {"URL", "Name", "Type", "Authentication", "ProxyType", "User", "Password"}
        additional = {k: v for k, v in cfg.items() if k not in well_known}
        dest = Destination(
            url=d_url,
            auth_type=cfg.get("Authentication", "NoAuthentication"),
            username=cfg.get("User"),
            password=cfg.get("Password"),
            additional=additional,
        )
        self._dest_cache[name] = (dest, time.monotonic() + DEST_CACHE_TTL)
        return dest


class N8nClient:
    """Async HTTP client for n8n webhook destinations."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        resolver: _DestinationResolver | None = None,
    ) -> None:
        self._timeout = timeout
        self._resolver = resolver or _DestinationResolver(timeout=timeout)

    def _auth(self, dest: Destination) -> httpx.BasicAuth | None:
        if dest.auth_type == "BasicAuthentication" and dest.username and dest.password:
            return httpx.BasicAuth(dest.username, dest.password)
        return None

    async def post(
        self,
        destination_name: str,
        path: str,
        body: dict[str, Any],
        user_identity: str | None = None,
    ) -> dict[str, Any]:
        """POST JSON body to an n8n webhook endpoint resolved from a BTP destination.

        Args:
            destination_name: BTP destination name (e.g. 'REPLENISHMENT_WORKFLOW')
            path:             Webhook path (e.g. '/replenishment-adjustment-received')
            body:             JSON payload
            user_identity:    Optional audit identity header

        Returns:
            Parsed JSON response, or {"error": True, ...} on failure
        """
        dest = await self._resolver.resolve(destination_name)
        if not path.startswith("/"):
            path = "/" + path
        url = f"{dest.url}{path}"
        headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
        if user_identity:
            headers["X-User-Identity"] = user_identity
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                url,
                json=body,
                auth=self._auth(dest),
                headers=headers,
            )
        if r.status_code >= 400:
            return {
                "error": True,
                "status_code": r.status_code,
                "message": r.text,
                "url": url,
            }
        try:
            return r.json()
        except Exception:
            return {"status_code": r.status_code, "raw": r.text}

    async def post_replenishment_adjustment(
        self,
        run_id: str,
        classifications: list[dict[str, Any]],
        user_identity: str | None = None,
    ) -> dict[str, Any]:
        """Trigger the replenishment adjustment workflow for seasonal articles."""
        return await self.post(
            REPLENISHMENT_DESTINATION_NAME,
            "/replenishment-adjustment-received",
            {"run_id": run_id, "classifications": classifications},
            user_identity=user_identity,
        )

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
        """Dispatch classification notifications to all stakeholder groups."""
        return await self.post(
            NOTIFICATION_DESTINATION_NAME,
            "/seasonal-article-detector-8a850/classification-notification-workflow/classification-notification-received",
            {
                "run_id": run_id,
                "run_date": run_date,
                "total_classified": total_classified,
                "seasonal_count": seasonal_count,
                "low_confidence_count": low_confidence_count,
                "dashboard_url": dashboard_url,
                "top_seasonal_articles": top_seasonal_articles or [],
            },
            user_identity=user_identity,
        )


__all__ = ["N8nClient", "Destination", "REPLENISHMENT_DESTINATION_NAME", "NOTIFICATION_DESTINATION_NAME"]
