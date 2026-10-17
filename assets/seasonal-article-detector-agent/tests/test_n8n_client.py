"""Unit tests for n8n_client.py — N8nClient backed by BTP destination service."""
import json
import os

import pytest
import pytest_asyncio

os.environ.setdefault("IBD_TESTING", "true")

# ---------------------------------------------------------------------------
# Minimal stub for httpx.AsyncClient used in n8n_client
# ---------------------------------------------------------------------------

class _StubResponse:
    def __init__(self, status_code: int = 200, body: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._body = body
        self.text = text or json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _StubAsyncClient:
    """Records calls; returns preset responses."""

    def __init__(self, responses: list[_StubResponse] | None = None):
        self._queue = list(responses or [])
        self.calls: list[dict] = []

    def _next(self) -> _StubResponse:
        if self._queue:
            return self._queue.pop(0)
        return _StubResponse(200, {"access_token": "tok-default", "destinationConfiguration": {}})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def get(self, url, **kwargs):
        self.calls.append({"method": "GET", "url": url, **kwargs})
        return self._next()

    async def post(self, url, **kwargs):
        self.calls.append({"method": "POST", "url": url, **kwargs})
        return self._next()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_vcap_empty_returns_none():
    import n8n_client as nc
    original = os.environ.pop("VCAP_SERVICES", None)
    try:
        assert nc._first_binding("destination") is None
    finally:
        if original is not None:
            os.environ["VCAP_SERVICES"] = original


def test_vcap_invalid_json_returns_empty(monkeypatch):
    import n8n_client as nc
    monkeypatch.setenv("VCAP_SERVICES", "not-json{{}}")
    assert nc._first_binding("destination") is None


def test_vcap_binding_resolved(monkeypatch):
    import n8n_client as nc
    vcap = {"destination": [{"credentials": {"clientid": "cid", "clientsecret": "cs", "url": "https://oauth", "uri": "https://dest"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))
    creds = nc._first_binding("destination")
    assert creds["clientid"] == "cid"


@pytest.mark.asyncio
async def test_destination_resolver_token_cached(monkeypatch):
    import n8n_client as nc
    import httpx
    vcap = {"destination": [{"credentials": {"clientid": "cid", "clientsecret": "cs", "url": "https://oauth", "uri": "https://dest"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))

    call_count = 0

    class _CountingClient(_StubAsyncClient):
        async def post(self, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return _StubResponse(200, {"access_token": "tok-abc"})

    monkeypatch.setattr(nc.httpx, "AsyncClient", lambda **_: _CountingClient())

    resolver = nc._DestinationResolver()
    t1 = await resolver._access_token()
    t2 = await resolver._access_token()
    assert t1 == t2 == "tok-abc"
    assert call_count == 1  # token cached; only one network call


@pytest.mark.asyncio
async def test_post_returns_json_on_success(monkeypatch):
    import n8n_client as nc
    import httpx
    vcap = {"destination": [{"credentials": {"clientid": "c", "clientsecret": "s", "url": "https://oauth", "uri": "https://dest"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))

    # token call → destination call → actual POST
    stub = _StubAsyncClient([
        _StubResponse(200, {"access_token": "tok"}),
        _StubResponse(200, {"destinationConfiguration": {"URL": "https://n8n.example.com", "Authentication": "NoAuthentication"}}),
        _StubResponse(200, {"processed_count": 2, "status": "completed"}),
    ])
    monkeypatch.setattr(nc.httpx, "AsyncClient", lambda **_: stub)

    client = nc.N8nClient()
    result = await client.post("REPLENISHMENT_WORKFLOW", "/replenishment-adjustment-received", {"run_id": "r1", "classifications": []})
    assert result["status"] == "completed"
    assert result["processed_count"] == 2


@pytest.mark.asyncio
async def test_post_returns_error_on_4xx(monkeypatch):
    import n8n_client as nc
    import httpx
    vcap = {"destination": [{"credentials": {"clientid": "c", "clientsecret": "s", "url": "https://oauth", "uri": "https://dest"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))

    stub = _StubAsyncClient([
        _StubResponse(200, {"access_token": "tok"}),
        _StubResponse(200, {"destinationConfiguration": {"URL": "https://n8n.example.com", "Authentication": "NoAuthentication"}}),
        _StubResponse(400, text="Bad Request"),
    ])
    monkeypatch.setattr(nc.httpx, "AsyncClient", lambda **_: stub)

    client = nc.N8nClient()
    result = await client.post("REPLENISHMENT_WORKFLOW", "/some-path", {})
    assert result["error"] is True
    assert result["status_code"] == 400


@pytest.mark.asyncio
async def test_post_replenishment_adjustment_helper(monkeypatch):
    import n8n_client as nc
    import httpx

    vcap = {"destination": [{"credentials": {"clientid": "c", "clientsecret": "s", "url": "https://oauth", "uri": "https://dest"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))

    stub = _StubAsyncClient([
        _StubResponse(200, {"access_token": "tok"}),
        _StubResponse(200, {"destinationConfiguration": {"URL": "https://n8n.example.com", "Authentication": "NoAuthentication"}}),
        _StubResponse(200, {"run_id": "run-1", "processed_count": 1, "status": "completed"}),
    ])
    monkeypatch.setattr(nc.httpx, "AsyncClient", lambda **_: stub)

    client = nc.N8nClient()
    result = await client.post_replenishment_adjustment("run-1", [{"article_id": "ART001", "classification": "SEASONAL", "confidence_score": 80}])
    assert result["run_id"] == "run-1"
    # Verify the path posted to
    post_call = stub.calls[-1]
    assert "/replenishment-adjustment-received" in post_call["url"]


@pytest.mark.asyncio
async def test_post_with_basic_auth(monkeypatch):
    import n8n_client as nc
    import httpx

    vcap = {"destination": [{"credentials": {"clientid": "c", "clientsecret": "s", "url": "https://oauth", "uri": "https://dest"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))

    stub = _StubAsyncClient([
        _StubResponse(200, {"access_token": "tok"}),
        _StubResponse(200, {"destinationConfiguration": {
            "URL": "https://n8n.example.com",
            "Authentication": "BasicAuthentication",
            "User": "admin",
            "Password": "secret",
        }}),
        _StubResponse(200, {"status": "ok"}),
    ])
    monkeypatch.setattr(nc.httpx, "AsyncClient", lambda **_: stub)

    client = nc.N8nClient()
    result = await client.post("SOME_DEST", "/some-path", {"key": "value"})
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_x_user_identity_header_injected(monkeypatch):
    """X-User-Identity header is sent when user_identity is provided."""
    import n8n_client as nc

    vcap = {"destination": [{"credentials": {"clientid": "c", "clientsecret": "s", "url": "https://oauth", "uri": "https://dest"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))

    recorded_post_headers: list[dict] = []
    call_count = [0]

    class _SequenceClient:
        """Returns preset responses in sequence; records POST headers on the 3rd call."""
        _responses = [
            _StubResponse(200, {"access_token": "tok"}),
            _StubResponse(200, {"destinationConfiguration": {"URL": "https://n8n.example.com", "Authentication": "NoAuthentication"}}),
            _StubResponse(200, {"status": "ok"}),
        ]

        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        async def get(self, url, **kwargs):
            call_count[0] += 1
            return self._responses[min(call_count[0] - 1, len(self._responses) - 1)]

        async def post(self, url, **kwargs):
            recorded_post_headers.append(dict(kwargs.get("headers", {})))
            call_count[0] += 1
            return self._responses[min(call_count[0] - 1, len(self._responses) - 1)]

    monkeypatch.setattr(nc.httpx, "AsyncClient", lambda **_: _SequenceClient())

    client = nc.N8nClient()
    await client.post("D", "/p", {}, user_identity="ALICE")
    assert any(h.get("X-User-Identity") == "ALICE" for h in recorded_post_headers)


@pytest.mark.asyncio
async def test_x_user_identity_not_sent_when_none(monkeypatch):
    """X-User-Identity header is NOT sent when user_identity is None."""
    import n8n_client as nc

    vcap = {"destination": [{"credentials": {"clientid": "c", "clientsecret": "s", "url": "https://oauth", "uri": "https://dest"}}]}
    monkeypatch.setenv("VCAP_SERVICES", json.dumps(vcap))

    recorded_post_headers: list[dict] = []
    call_count = [0]

    class _SequenceClient:
        _responses = [
            _StubResponse(200, {"access_token": "tok"}),
            _StubResponse(200, {"destinationConfiguration": {"URL": "https://n8n.example.com", "Authentication": "NoAuthentication"}}),
            _StubResponse(200, {"status": "ok"}),
        ]

        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass

        async def get(self, url, **kwargs):
            call_count[0] += 1
            return self._responses[min(call_count[0] - 1, len(self._responses) - 1)]

        async def post(self, url, **kwargs):
            recorded_post_headers.append(dict(kwargs.get("headers", {})))
            call_count[0] += 1
            return self._responses[min(call_count[0] - 1, len(self._responses) - 1)]

    monkeypatch.setattr(nc.httpx, "AsyncClient", lambda **_: _SequenceClient())

    client = nc.N8nClient()
    await client.post("D", "/p", {}, user_identity=None)
    assert not any("X-User-Identity" in h for h in recorded_post_headers)
