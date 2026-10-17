import logging
import os

from a2a.server.agent_execution import AgentExecutor as A2AAgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

from agent import SampleAgent
from load_skill_resources import get_load_skill_resource_tool
from prompt_injection_detector import wrap_tool
from tools import (
    read_carab_timeseries,
    run_seasonality_detection,
    persist_classifications,
    get_classification_results,
    get_run_status,
    trigger_replenishment_adjustment,
    send_classification_notification,
)

# MCP tools are only loaded on Joule (JOULE_RUNTIME=1).
# On CF the Agent Gateway SDK is not available.
if os.environ.get("JOULE_RUNTIME"):
    from mcp_providers.agw import get_mcp_tools  # noqa: E402
else:
    async def get_mcp_tools() -> list:  # type: ignore[misc]
        return []

logger = logging.getLogger(__name__)

# All domain tools — the same set runs on both runtimes.
# On Joule: MCP tools are added at runtime from the Agent Gateway.
# On CF:    trigger_replenishment_adjustment and send_classification_notification
#           call N8nClient directly via BTP destinations.
_DOMAIN_TOOLS = [
    read_carab_timeseries,
    run_seasonality_detection,
    persist_classifications,
    get_classification_results,
    get_run_status,
    trigger_replenishment_adjustment,
    send_classification_notification,
]


class AgentExecutor(A2AAgentExecutor):
    def __init__(self):
        self.agent = SampleAgent()
        self.skill_tools = get_load_skill_resource_tool()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute the agent and stream results back via A2A protocol.

        On Joule: MCP tools are loaded from Agent Gateway and merged with domain tools.
        On CF: only domain tools are used; MCP gateway is not available.

        Args:
            context: Request context containing user input and task info
            event_queue: Queue for publishing task status updates

        Raises:
            ServerError: On unrecoverable agent execution errors
        """
        query = context.get_user_input()
        task = context.current_task
        if not task:
            assert context.message is not None, "Cannot create task without a message"
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        # On Joule: load MCP tools from Agent Gateway (workflow webhooks via MCP)
        # On CF:    get_mcp_tools() returns [] — workflow tools are in _DOMAIN_TOOLS
        mcp_tools = []
        try:
            mcp_tools = await get_mcp_tools()
            if mcp_tools:
                tool_names = [t.name for t in mcp_tools]
                logger.info("Loaded %d MCP tool(s) for agent execution: %s", len(mcp_tools), tool_names)
        except Exception as e:
            logger.error("Failed to load MCP tools: %s", e)

        all_tools = [*mcp_tools, *_DOMAIN_TOOLS, *self.skill_tools]

        # Wrap all tools with prompt injection scanning
        all_tools = [wrap_tool(t) for t in all_tools]

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            async for item in self.agent.stream(query, task.context_id, tools=all_tools):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]
                content = item["content"]

                if require_user_input:
                    await updater.update_status(
                        TaskState.input_required,
                        new_agent_text_message(content, task.context_id, task.id),
                        final=True,
                    )
                    break
                elif is_task_complete:
                    await updater.add_artifact(
                        [Part(root=TextPart(text=content))], name="agent_result"
                    )
                    await updater.complete()
                    break
                else:
                    await updater.update_status(
                        TaskState.working,
                        new_agent_text_message(content, task.context_id, task.id),
                    )
        except Exception as e:
            logger.exception("Agent execution error")
            raise ServerError(error=InternalError()) from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())
