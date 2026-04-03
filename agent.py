"""
agent.py — DevMind's Brain
Inspired by Claude Code's query.ts + QueryEngine.ts.
Uses LangGraph to communicate with the Claude API and execute tools.

Features:
  - Task tracking (task.py)
  - Real-time streaming (chat_stream)
  - Auto retry on failure (configurable attempts)
  - Cost tracking on all paths
  - Custom exception handling
"""

import os
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
from logger import log
from task import (
    TaskType, TaskStatus,
    create_task, complete_task, fail_task, get_duration,
)

load_dotenv()


# ============================================================
# Agent State
# ============================================================
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ============================================================
# DevMind Agent
# ============================================================
class DevMindAgent:
    """
    Main agent class — manages the LangGraph graph,
    communicates with the Claude API, and executes tools.
    """

    def __init__(self, model: str | None = None):
        self.model_name = model or config.model.name

        if not config.api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY not found!\n"
                "Add it to your .env file: ANTHROPIC_API_KEY=sk-ant-..."
            )

        init_tracker(self.model_name)
        register_exit_hook()

        # Main LLM — with tools bound
        self.llm = ChatAnthropic(
            model=self.model_name,
            api_key=config.api_key,
            max_tokens=config.model.max_tokens,
            streaming=config.model.streaming,
        ).bind_tools(ALL_TOOLS)

        self.graph = self._build_graph()
        self.system_prompt: str = build_system_prompt()
        self.task_history: list = []

        log.info(f"DevMind Agent initialized with model: {self.model_name}")

    # ----------------------------------------------------------
    # LangGraph Graph
    # ----------------------------------------------------------
    def _build_graph(self) -> StateGraph:
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

    def _claude_node(self, state: AgentState) -> AgentState:
        """Call Claude and get a response."""
        messages = [SystemMessage(content=self.system_prompt)] + state["messages"]
        response = self.llm.invoke(messages)

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            track_call(
                input_tokens=response.usage_metadata.get("input_tokens", 0),
                output_tokens=response.usage_metadata.get("output_tokens", 0),
                model=self.model_name,
            )

        return {"messages": [response]}

    @staticmethod
    def _should_use_tool(state: AgentState) -> str:
        """Decide whether to call a tool or return the response."""
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "use_tool"
        return "done"

    # ----------------------------------------------------------
    # chat() — with retry logic
    # ----------------------------------------------------------
    def chat(self, user_input: str, history: list[BaseMessage] | None = None) -> str:
        """
        Accept a user message, process it through the agent, and return a response.
        Retries on failure up to the configured maximum attempts.

        Args:
            user_input: The user's message
            history: Previous conversation messages

        Returns:
            The agent's response text

        Raises:
            RetryExhaustedError: If all retries are exhausted
        """
        task = create_task(TaskType.AGENT, user_input[:80])
        task.status = TaskStatus.RUNNING
        self.task_history.append(task)

        last_error: Exception | None = None
        max_retries = config.retry.max_retries

        for attempt in range(1, max_retries + 1):
            try:
                messages = list(history or [])
                messages.append(HumanMessage(content=user_input))

                result = self.graph.invoke({"messages": messages})
                response_text = self._extract_text(result["messages"])

                complete_task(task, f"{len(response_text)} chars")
                log.debug(f"chat() succeeded on attempt {attempt}")
                return response_text

            except Exception as e:
                last_error = e
                error_msg = str(e)

                is_retryable = any(
                    code in error_msg for code in config.retry.retryable_codes
                )

                if is_retryable and attempt < max_retries:
                    wait = config.retry.base_delay * attempt
                    log.warning(
                        f"Retry {attempt}/{max_retries}: {error_msg[:60]}... "
                        f"waiting {wait}s"
                    )
                    time.sleep(wait)
                    continue
                else:
                    break

        fail_task(task, str(last_error))
        raise RetryExhaustedError(max_retries, last_error)

    # ----------------------------------------------------------
    # chat_stream() — Real-time token streaming
    # ----------------------------------------------------------
    def chat_stream(self, user_input: str, history: list[BaseMessage] | None = None) -> Iterator[str]:
        """
        Yield the response token by token for real-time display.
        First attempts LLM streaming — switches to the graph if a tool call is detected.

        Args:
            user_input: The user's message
            history: Previous conversation messages

        Yields:
            Response text chunks
        """
        messages = [SystemMessage(content=self.system_prompt)]
        messages += list(history or [])
        messages.append(HumanMessage(content=user_input))

        try:
            collected_text = ""
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
            else:
                # Pure text response — track cost (usage not available in streaming)
                approx_input = sum(len(str(m.content)) // 4 for m in messages)
                approx_output = len(collected_text) // 4
                track_call(
                    input_tokens=approx_input,
                    output_tokens=approx_output,
                    model=self.model_name,
                )

        except Exception as e:
            log.error(f"Streaming failed, falling back to chat(): {e}")
            response = self.chat(user_input, history)
            yield response

    # ----------------------------------------------------------
    # Helper: Extract text from messages
    # ----------------------------------------------------------
    @staticmethod
    def _extract_text(messages: list[BaseMessage]) -> str:
        """
        Extract the last AI response text from a messages list.

        Args:
            messages: Messages returned by LangGraph

        Returns:
            Extracted text string
        """
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
    def get_history_messages(history: list[dict[str, str]]) -> list[BaseMessage]:
        """
        Convert dict-based history to LangChain message objects.

        Args:
            history: List of {"role": "user"/"assistant", "content": "..."}

        Returns:
            List of LangChain message objects
        """
        messages: list[BaseMessage] = []
        for item in history:
            if item["role"] == "user":
                messages.append(HumanMessage(content=item["content"]))
            elif item["role"] == "assistant":
                messages.append(AIMessage(content=item["content"]))
        return messages

    def get_task_summary(self) -> str:
        """
        Return a summary of all tasks in this session.

        Returns:
            Formatted task summary string
        """
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
                icon = "✅"
            elif t.status == TaskStatus.FAILED:
                icon = "❌"
            else:
                icon = "⏳"
            lines.append(f"  {icon} [{t.id}] {t.description[:50]} ({dur_str})")

        return "\n".join(lines)


if __name__ == "__main__":
    agent = DevMindAgent()
    response = agent.chat("Hello! What can you do?")
    print(response)
    print(agent.get_task_summary())
