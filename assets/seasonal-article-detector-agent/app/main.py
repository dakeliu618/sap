import os

# ── Joule/Kyma telemetry: run whenever sap_cloud_sdk is available ─────────────
# set_aicore_config() MUST be called before any AI framework import.
# It runs on all Joule environments (deployed, preview-with-mock, test) where
# sap_cloud_sdk is installed. On CF it is silently skipped (not installed).
try:
    from sap_cloud_sdk.aicore import set_aicore_config
    from sap_cloud_sdk.core.telemetry import auto_instrument
    set_aicore_config()
    auto_instrument()
except ImportError:
    pass  # CF runtime — sap_cloud_sdk not installed, skip silently
# ─────────────────────────────────────────────────────────────────────────────

import argparse
import logging

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from starlette.middleware.base import BaseHTTPMiddleware

from agent_executor import AgentExecutor

# JWTContextMiddleware only reads/stores the token for Agent Gateway (Joule).
# On CF the middleware still runs harmlessly — it just sets a context var that
# get_mcp_tools() never reads (returns [] on CF).
try:
    from mcp_providers.agw import set_user_token, reset_user_token
    from sap_cloud_sdk import bootstrap
except ImportError:
    # CF runtime — provide no-op stubs
    def set_user_token(token):  # type: ignore[misc]
        from contextvars import ContextVar
        _ctx: ContextVar = ContextVar("_noop_token", default=None)
        return _ctx.set(token)

    def reset_user_token(ctx):  # type: ignore[misc]
        ctx.var.reset(ctx)

    def bootstrap(app):  # type: ignore[misc]
        pass  # no-op on CF

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))

# Allow --port CLI arg so the Joule Studio preview panel (and conftest.py
# start_agent fixture) can pick a free port at startup time.
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--port", type=int, default=None)
_args, _ = _parser.parse_known_args()
if _args.port is not None:
    PORT = _args.port


def build_app():
    """Build the A2A Starlette application. Called by gunicorn at startup."""
    skill = AgentSkill(
        id="seasonal-article-detector-agent",
        name="seasonal-article-detector-agent",
        description=(
            "An AI agent that automatically detects strongly seasonal articles from "
            "historical article/store level sales time-series data in SAP Customer "
            "Activity Repository (CAR/CARAB), classifies them with a confidence score "
            "and season window, and triggers downstream replenishment and notification workflows."
        ),
        tags=["seasonal", "article", "detector", "agent"],
        examples=[
            "Run seasonal classification for all articles in store S001",
            "Which articles are strongly seasonal in category APPAREL?",
        ],
    )
    agent_card = AgentCard(
        name="seasonal-article-detector-agent",
        description=(
            "An AI agent that automatically detects strongly seasonal articles from "
            "historical article/store level sales time-series data in SAP Customer "
            "Activity Repository (CAR/CARAB), classifies them with a confidence score "
            "and season window, and triggers downstream replenishment and notification workflows."
        ),
        url=os.environ.get("AGENT_PUBLIC_URL", f"http://localhost:{PORT}/"),
        version="1.0.0",
        default_input_modes=["text", "text/plain"],
        default_output_modes=["text", "text/plain"],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        skills=[skill],
    )
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=DefaultRequestHandler(
            agent_executor=AgentExecutor(),
            task_store=InMemoryTaskStore(),
        ),
    )
    app = server.build()

    class JWTContextMiddleware(BaseHTTPMiddleware):
        """Extracts JWT token from Authorization header and stores in context var."""

        async def dispatch(self, request, call_next):
            auth_header = request.headers.get("authorization", "")
            token = auth_header[7:] if auth_header.lower().startswith("bearer ") else None
            token_ctx = set_user_token(token)
            try:
                return await call_next(request)
            finally:
                reset_user_token(token_ctx)

    app.add_middleware(JWTContextMiddleware)
    bootstrap(app)
    return app


# gunicorn expects a module-level `application` callable.
# `--chdir app main:application` resolves this after cd-ing into app/.
application = build_app()

if __name__ == "__main__":
    logger.info("Starting A2A server at http://%s:%s", HOST, PORT)
    uvicorn.run(application, host=HOST, port=PORT)
