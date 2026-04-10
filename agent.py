"""
agent.py — DevMind's Brain
Uses LangGraph to communicate with the Claude API and execute tools.

Features:
  - Task tracking (task.py)
  - Real-time streaming (chat_stream)
  - Exponential backoff retry with jitter (retry_config)
  - Client-side rate limiting (rate_limiter)
  - Cost tracking on ALL paths including errors
  - Performance metrics (latency, success rate, retries)
  - Custom exception handling
"""

from __future__ import annotations

import random
import time
from typing import Annotated, TypedDict, Iterator

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from config import config
from context import build_system_prompt
from tools import ALL_TOOLS
from cost_tracker import track_call, init_tracker, register_exit_hook
from exceptions import ConfigError, RetryExhaustedError
from logger import get_logger
from metrics import record_request
from rate_limiter import acquire_or_raise
from task import (
    TaskType, TaskStatus,
    create_task, complete_task, fail_task, get_duration,
)

load_dotenv()
log = get_logger("agent")


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


def _compute_backoff(attempt: int) -> float:
    """Exponential backoff with full jitter. attempt is 1-indexed."""
    retry = config.retry
    raw = retry.base_delay * (retry.backoff_factor ** (attempt - 1))
    capped = min(raw, retry.max_delay)
    jitter = capped * retry.jitter
    return max(0.0, capped + random.uniform(-jitter, jitter))


def _is_retryable(error: Exception) -> bool:
    msg = str(error)
    return any(code in msg for code in config.retry.retryable_codes)


class DevMindAgent:
    """
    Main agent class — manages the LangGraph graph,
    communicates with the Claude API, and executes tools.
    """

    def __init__(self, model=None):
        self.model_name = model or config.model.name

        if not config.api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY not found!\n"
                "Add it to your .env file: ANTHROPIC_API_KEY=sk-ant-..."
            )

        init_tracker(self.model_name)
        register_exit_hook()

        self.llm = ChatAnthropic(
            model=self.model_name,
            api_key=config.api_key,
            max_tokens=config.model.max_tokens,
            streaming=config.model.streaming,
        ).bind_tools(ALL_TOOLS)

        self.graph = self._build_graph()
        self.system_prompt = build_system_prompt()
        self.task_history = []

        log.info(f"DevMind Agent initialized with model: {self.model_name}")

    def _build_graph(self):
        """Build the LangGraph agent loop."""
        graph = StateGraph(AgentState)
        graph.add_node("claude", self._claude_node)
        graph.add_node("tools", ToolNode(ALL_TOOLS))
        graph.set_entry_point("claude")
        graph.add_conditional_edges(
            "claude",
            self._should_use_tool,
            {"use_tool": "tools", "done": END},
        )
        graph.add_edge("tools", "claude")
        return graph.compile()

    def _claude_node(self, state):
        """Call Claude and get a response."""
        messages = [SystemMessage(content=self.system_prompt)] + state["messages"]

        acquire_or_raise(cost=1.0)

        response = self.llm.invoke(messages)

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            track_call(
                input_tokens=response.usage_metadata.get("input_tokens", 0),
                output_tokens=response.usage_metadata.get("output_tokens", 0),
                model=self.model_name,
            )

        return {"messages": [response]}

    @staticmethod
    def _should_use_tool(state):
        """Decide whether to call a tool or return the response."""
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "use_tool"
        return "done"

    def chat(self, user_input, history=None):
        """
        Process a user message through the agent with retry logic.
        Retries with exponential backoff on transient failures.
        """
        task = create_task(TaskType.AGENT, user_input[:80])
        task.status = TaskStatus.RUNNING
        self.task_history.append(task)

        last_error = None
        max_retries = config.retry.max_retries
        retries_used = 0
        start = time.monotonic()
        success = False

        try:
            for attempt in range(1, max_retries + 1):
                try:
                    messages = list(history or [])
                    messages.append(HumanMessage(content=user_input))

                    result = self.graph.invoke({"messages": messages})
                    response_text = self._extract_text(result["messages"])

                    complete_task(task, f"{len(response_text)} chars")
                    log.debug(f"chat() succeeded on attempt {attempt}")
                    success = True
                    return response_text

                except Exception as e:
                    last_error = e
                    error_msg = str(e)

                    if _is_retryable(e) and attempt < max_retries:
                        retries_used += 1
                        wait = _compute_backoff(attempt)
                        log.warning(
                            f"Retry {attempt}/{max_retries}: "
                            f"{error_msg[:80]} — waiting {wait:.2f}s"
                        )
                        time.sleep(wait)
                        continue
                    break

            fail_task(task, str(last_error))
            raise RetryExhaustedError(max_retries, last_error)
        finally:
            record_request(
                duration=time.monotonic() - start,
                success=success,
                retries=retries_used,
            )

    def chat_stream(self, user_input, history=None):
        """
        Yield the response token by token for real-time display.
        First attempts LLM streaming — switches to the graph if a tool call is detected.
        """
        messages = [SystemMessage(content=self.system_prompt)]
        messages += list(history or [])
        messages.append(HumanMessage(content=user_input))

        start = time.monotonic()
        success = False
        collected_text = ""

        try:
            acquire_or_raise(cost=1.0)

            has_tool_calls = False

            for chunk in self.llm.stream(messages):
                if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                    has_tool_calls = True
                    break

                if hasattr(chunk, "content") and chunk.content:
                    if isinstance(chunk.content, str):
                        collected_text += chunk.content
                        yield chunk.content
                    elif isinstance(chunk.content, list):
                        for part in chunk.content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text = part.get("text", "")
                                collected_text += text
                                yield text

            if has_tool_calls:
                log.debug("Tool call detected in stream, switching to graph")
                response = self.chat(user_input, history)
                if collected_text and response.startswith(collected_text):
                    yield response[len(collected_text):]
                else:
                    yield response
                success = True
            else:
                approx_input = sum(len(str(m.content)) // 4 for m in messages)
                approx_output = len(collected_text) // 4
                track_call(
                    input_tokens=approx_input,
                    output_tokens=approx_output,
                    model=self.model_name,
                )
                success = True

        except Exception as e:
            log.error(f"Streaming failed, falling back to chat(): {e}")
            if collected_text:
                track_call(
                    input_tokens=sum(len(str(m.content)) // 4 for m in messages),
                    output_tokens=len(collected_text) // 4,
                    model=self.model_name,
                )
            try:
                response = self.chat(user_input, history)
                yield response
                success = True
            except Exception as inner:
                log.error(f"Fallback chat() also failed: {inner}")
                raise
        finally:
            record_request(
                duration=time.monotonic() - start,
                success=success,
                retries=0,
            )

    @staticmethod
    def _extract_text(messages):
        """Extract the last AI response text from a messages list."""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                if isinstance(msg.content, list):
                    parts = [
                        p["text"] for p in msg.content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    if parts:
                        return " ".join(parts)
                elif isinstance(msg.content, str):
                    return msg.content
        return "(No response received)"

    @staticmethod
    def get_history_messages(history):
        """Convert dict-based history to LangChain message objects."""
        messages = []
        for item in history:
            if item["role"] == "user":
                messages.append(HumanMessage(content=item["content"]))
            elif item["role"] == "assistant":
                messages.append(AIMessage(content=item["content"]))
        return messages

    def get_task_summary(self):
        """Return a summary of all tasks in this session."""
        if not self.task_history:
            return "No tasks have run yet."

        completed = sum(1 for t in self.task_history if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.task_history if t.status == TaskStatus.FAILED)
        total = len(self.task_history)

        lines = [f"Tasks: {total} total | {completed} completed | {failed} failed"]
        for t in self.task_history[-5:]:
            dur = get_duration(t)
            dur_str = f"{dur}s" if dur else "..."
            if t.status == TaskStatus.COMPLETED:
                icon = "OK"
            elif t.status == TaskStatus.FAILED:
                icon = "XX"
            else:
                icon = ".."
            lines.append(f"  {icon} [{t.id}] {t.description[:50]} ({dur_str})")

        return "\n".join(lines)


if __name__ == "__main__":
    agent = DevMindAgent()
    response = agent.chat("Hello! What can you do?")
    print(response)
    print(agent.get_task_summary())
