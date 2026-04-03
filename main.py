"""
main.py — DevMind's Entry Point
Inspired by Claude Code's main.tsx.
Ties everything together and starts the terminal REPL.

Features:
  - Real-time streaming display
  - Smart conversation history management
  - Slash commands (/help, /cost, /tasks, /clear, /cd, /exit)
  - Graceful error handling
"""

import os
import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.markdown import Markdown
except ImportError:
    print("Please install the Rich library: pip install rich")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Please install python-dotenv: pip install python-dotenv")
    sys.exit(1)

from config import config
from logger import log

console = Console()


# ============================================================
# Welcome Banner
# ============================================================
def show_banner() -> None:
    """Display the welcome banner in the terminal."""
    banner = Text()
    banner.append("  DevMind  ", style="bold white on blue")
    banner.append("  AI Coding Assistant", style="dim")

    console.print()
    console.print(Panel(
        banner,
        subtitle="[dim]Inspired by Claude Code • Python + LangGraph • Streaming[/dim]",
        border_style="blue",
        padding=(0, 2),
    ))
    console.print(
        "[dim]Commands: [bold]/help[/bold] · [bold]/cost[/bold] · "
        "[bold]/tasks[/bold] · [bold]/clear[/bold] · [bold]/exit[/bold][/dim]"
    )
    console.print()


# ============================================================
# Help Message
# ============================================================
def show_help() -> None:
    """Display the help panel."""
    help_text = """
[bold]DevMind — How to Use:[/bold]

[cyan]Normal use:[/cyan]
  Just type any coding question!
  "what files are in this folder?"
  "are there any bugs in main.py?"
  "create a file called hello_world.py"
  "fix line 5 in main.py"

[cyan]Slash commands:[/cyan]
  [bold]/help[/bold]          — Show this help message
  [bold]/cost[/bold]          — Show API cost so far (tokens + USD)
  [bold]/tasks[/bold]         — Show all tasks in this session
  [bold]/clear[/bold]         — Clear chat history
  [bold]/exit[/bold]          — Exit DevMind
  [bold]/cd <path>[/bold]     — Change working directory

[cyan]Tips:[/cyan]
  • DevMind will read, edit, and run files on its own
  • Be specific: "find the Y function in file X"
  • To edit: "change the timeout in tools.py from 30 to 60"
"""
    console.print(Panel(help_text.strip(), border_style="dim", title="[dim]Help[/dim]"))


# ============================================================
# Smart Conversation History Management
# ============================================================
def smart_truncate_history(
    history: list[dict[str, str]],
    max_messages: int | None = None,
    summary_threshold: int | None = None,
) -> list[dict[str, str]]:
    """
    Keep conversation history manageable by summarizing old messages.
    Preserves recent messages while compressing older ones into a summary.

    Args:
        history: Full conversation history
        max_messages: Maximum number of messages to keep
        summary_threshold: Summarize once history exceeds this length

    Returns:
        Truncated / summarized history
    """
    max_msgs = max_messages or config.history.max_messages
    threshold = summary_threshold or config.history.summary_threshold

    if len(history) <= threshold:
        return history

    old_messages = history[:len(history) - max_msgs + 2]
    recent_messages = history[len(history) - max_msgs + 2:]

    # Build a brief summary of the older messages
    summary_parts: list[str] = []
    for msg in old_messages:
        role = "User" if msg["role"] == "user" else "DevMind"
        content_preview = msg["content"][:100]
        summary_parts.append(f"- {role}: {content_preview}")

    summary_text = (
        "[Previous conversation summary]\n"
        + "\n".join(summary_parts[-6:])
        + "\n[End of summary]"
    )

    summarized = [
        {"role": "user", "content": summary_text},
        {"role": "assistant", "content": "Understood, I have the previous context."},
    ]

    log.debug(
        f"History truncated: {len(history)} → {len(summarized) + len(recent_messages)} messages"
    )
    return summarized + recent_messages


# ============================================================
# Slash Commands
# ============================================================
def handle_slash_command(
    cmd: str,
    history: list[dict[str, str]],
    agent,
) -> tuple[bool, list[dict[str, str]]]:
    """
    Handle a slash command.

    Args:
        cmd: Command string (e.g., "/help")
        history: Current conversation history
        agent: DevMindAgent instance

    Returns:
        (should_continue, updated_history)
    """
    cmd = cmd.strip().lower()

    if cmd in ("/exit", "/quit"):
        console.print("\n[dim]Shutting down DevMind... Goodbye![/dim]\n")
        return False, history

    elif cmd == "/help":
        show_help()

    elif cmd == "/cost":
        from cost_tracker import format_cost_summary
        console.print(Panel(
            format_cost_summary(),
            title="[dim]Session Cost[/dim]",
            border_style="dim",
        ))

    elif cmd == "/tasks":
        summary = agent.get_task_summary()
        console.print(Panel(
            summary,
            title="[dim]Task History[/dim]",
            border_style="dim",
        ))

    elif cmd == "/clear":
        history.clear()
        console.clear()
        show_banner()
        console.print("[dim]Chat history cleared.[/dim]\n")

    elif cmd.startswith("/cd "):
        new_dir = cmd[4:].strip()
        try:
            os.chdir(new_dir)
            from context import build_system_prompt
            agent.system_prompt = build_system_prompt()
            console.print(f"[dim]Working directory: {os.getcwd()}[/dim]")
            log.info(f"Working directory changed: {os.getcwd()}")
        except FileNotFoundError:
            console.print(f"[red]Directory not found: {new_dir}[/red]")

    else:
        console.print(f"[red]Unknown command: {cmd}[/red] — [dim]type /help[/dim]")
        return True, history

    return True, history


# ============================================================
# Streaming Response Display
# ============================================================
def display_streaming_response(agent, user_input: str, lc_history: list) -> str:
    """
    Stream Claude's response token by token to the terminal.

    Args:
        agent: DevMindAgent instance
        user_input: The user's message
        lc_history: LangChain-formatted history

    Returns:
        Full response text
    """
    console.print("[bold green]DevMind:[/bold green]")

    full_response = ""
    buffer = ""

    try:
        for chunk in agent.chat_stream(user_input, lc_history):
            full_response += chunk
            buffer += chunk

            if "\n" in buffer or len(buffer) > 80:
                console.print(buffer, end="", highlight=False)
                buffer = ""

        if buffer:
            console.print(buffer, end="", highlight=False)

        console.print()  # Final newline

    except Exception as e:
        log.error(f"Streaming display error: {e}")
        if not full_response:
            full_response = agent.chat(user_input, lc_history)
            try:
                console.print(Markdown(full_response))
            except Exception:
                console.print(full_response)

    console.print()
    return full_response


# ============================================================
# Main REPL Loop
# ============================================================
def run_repl() -> None:
    """Run the interactive REPL loop."""
    console.print("[dim]Starting DevMind...[/dim]", end="")

    try:
        from agent import DevMindAgent
        agent = DevMindAgent()
        console.print(" [green]Ready![/green]\n")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if "API_KEY" in str(e):
            console.print(
                "\n[dim]Fix: Add your Anthropic API key to a .env file:\n"
                "ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxx[/dim]"
            )
        sys.exit(1)

    conversation_history: list[dict[str, str]] = []

    while True:
        try:
            console.print(f"[dim]{os.getcwd()}[/dim]")
            user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                should_continue, conversation_history = handle_slash_command(
                    user_input, conversation_history, agent
                )
                if not should_continue:
                    break
                continue

            console.print()
            lc_history = agent.get_history_messages(conversation_history)

            response = display_streaming_response(agent, user_input, lc_history)

            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": response})

            # Smart history management
            conversation_history = smart_truncate_history(conversation_history)

        except KeyboardInterrupt:
            console.print("\n\n[dim]Ctrl+C detected — shutting down...[/dim]")
            break
        except EOFError:
            break
        except Exception as e:
            log.error(f"REPL error: {e}")
            console.print(f"\n[red]Error: {e}[/red]\n")
            continue


# ============================================================
# Entry Point
# ============================================================
def main() -> None:
    """Start DevMind."""
    show_banner()
    run_repl()


if __name__ == "__main__":
    main()
