"""Resolve SAP AI Core credentials from a BTP destination and create an LLM.

Single helper: init_llm_from_destination(). Reads the destination named
AICORE_DESTINATION_NAME (default 'aicore') via the destination service binding,
pushes AICORE_* env vars that gen_ai_hub reads, and returns a LangChain
BaseChatModel via init_llm.

The same destination service binding used by the n8n_client is used here
(proj-vector-destination-service). No separate xsuaa binding needed.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

# gen_ai_hub is only available on CF (installed via sap-ai-sdk-gen in requirements.txt).
# On Joule this module is never imported; the try/except keeps pylint happy.
try:
    from gen_ai_hub.proxy import set_proxy_version  # pylint: disable=import-error
    from gen_ai_hub.proxy.langchain.init_models import init_llm  # pylint: disable=import-error
except ImportError:  # Joule runtime — not needed there
    set_proxy_version = None  # type: ignore[assignment]
    init_llm = None  # type: ignore[assignment]

# Import resolver from n8n_client — it owns the destination service binding logic.
from n8n_client import _DestinationResolver, _first_binding

logger = logging.getLogger(__name__)

if set_proxy_version is not None:
    set_proxy_version("gen-ai-hub")

AICORE_DESTINATION_ENV = "AICORE_DESTINATION_NAME"
DEFAULT_AICORE_DESTINATION = "aicore"

_resolver = _DestinationResolver()


async def _get_access_token() -> str:
    """Fetch an access token for the destination service (delegated to _DestinationResolver)."""
    return await _resolver.access_token()


async def _fetch_destination_raw(name: str) -> dict[str, Any]:
    creds = _first_binding("destination") or {}
    if not creds:
        raise RuntimeError("No 'destination' service binding found in VCAP_SERVICES.")
    token = await _get_access_token()
    uri = creds["uri"].rstrip("/")
    url = f"{uri}/destination-configuration/v1/destinations/{name}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    if r.status_code >= 400:
        raise RuntimeError(
            f"Destination service returned {r.status_code} for '{name}': {r.text}"
        )
    return r.json()


async def init_llm_from_destination(
    model_name: str,
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    destination_name: str | None = None,
) -> Any:
    """Resolve the AI Core BTP destination and return a LangChain BaseChatModel.

    Idempotent: if AICORE_BASE_URL is already set (e.g. by a prior call or by
    manual env var injection), skips the destination resolution and calls
    init_llm directly.

    Args:
        model_name:       Model deployment name (e.g. 'gpt-4o')
        temperature:      Sampling temperature (default 0.0 for deterministic output)
        max_tokens:       Optional max output tokens
        destination_name: Override the BTP destination name (default: 'aicore')

    Returns:
        A LangChain BaseChatModel backed by SAP AI Core / gen-ai-hub
    """
    name = destination_name or os.environ.get(AICORE_DESTINATION_ENV, DEFAULT_AICORE_DESTINATION)

    if not os.environ.get("AICORE_BASE_URL"):
        payload = await _fetch_destination_raw(name)
        cfg = payload.get("destinationConfiguration") or {}

        base_url = (cfg.get("URL") or "").rstrip("/")
        client_id = cfg.get("clientId") or ""
        client_secret = cfg.get("clientSecret") or ""
        token_url = cfg.get("tokenServiceURL") or ""
        resource_group = (
            cfg.get("URL.headers.AI-Resource-Group")
            or cfg.get("AI_RESOURCE_GROUP")
            or "default"
        )

        if not (base_url and client_id and client_secret and token_url):
            raise RuntimeError(
                f"Destination '{name}' is missing one of URL / clientId / "
                f"clientSecret / tokenServiceURL. Got keys: {sorted(cfg.keys())}"
            )

        os.environ["AICORE_BASE_URL"] = base_url
        os.environ["AICORE_AUTH_URL"] = token_url
        os.environ["AICORE_CLIENT_ID"] = client_id
        os.environ["AICORE_CLIENT_SECRET"] = client_secret
        os.environ["AICORE_RESOURCE_GROUP"] = resource_group
        logger.info(
            "aicore destination '%s' resolved (base=%s, group=%s)",
            name, base_url, resource_group,
        )

    kwargs: dict[str, Any] = {"temperature": temperature}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return init_llm(model_name, **kwargs)
