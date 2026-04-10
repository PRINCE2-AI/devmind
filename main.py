"""
main.py — DevMind's Entry Point
Ties everything together and starts the terminal REPL.

Features:
  - Real-time streaming display
  - Smart conversation history management
  - Slash commands: /help /cost /metrics /tasks /history /save /load
                    /sessions /delete /cd /clear /exit
  - Graceful error handling
  - Autosave every N turns (configurable)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.markdown import Markdown
    from rich.table import Table
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
from logger import get_logger

log = get_logger("main")
console = Console()


def show_banner():
    """Display the welcome banner in the terminal."""
    banner = Text()
    banner.append("  DevMind  ", style="bold white on blue")
    banner.append("  AI Coding Assistant", style="dim")

    console.print()
    console.print(Panel(
        banner,
        subtitle="[dim]Inspired by Claude Code . Python + LangGraph . Streaming[/dim]",
        border_style="blue",
        padding=(0, 2),
    ))
    console.print(
        "[dim]Commands: [bold]/help[/bold] . [bold]/cost[/bold] . "
        "[bold]/metrics[/bold] . [bold]/save[/bold] . [bold]/load[/bold] . "
        "[bold]/exit[/bold][/dim]"
    )
    console.print()


def show_help():
    """Display the help panel."""
    help_text = """
[bold]DevMind - How to Use:[/bold]

[cyan]Normal use:[/cyan]
  Just type any coding question!
  "what files are in this folder?"
  "are there any bugs in main.py?"
  "create a file called hello_world.py"

[cyan]Slash commands:[/cyan]
  [bold]/help[/bold]              - Show this help message
  [bold]/cost[/bold]              - Show API cost so far (tokens + USD)
  [bold]/metrics[/bold]           - Show latency / success / retry metrics
  [bold]/tasks[/bold]             - Show all tasks in this session
  [bold]/history[/bold]           - Print current conversation history
  [bold]/save <name>[/bold]       - Save conversation under <name>
  [bold]/load <name>[/bold]       - Load a saved conversation
  [bold]/sessions[/bold]          - List saved conversations
  [bold]/delete <name>[/bold]     - Delete a saved conversation
  [bold]/clear[/bold]             - Clear chat history
  [bold]/cd <path>[/bold]         - Change working directory
  [bold]/exit[/bold]              - Exit DevMind

[cyan]Tips:[/cyan]
  . DevMind will read, edit, and run files on its own
  . Be specific: "find the Y function in file X"
  . Drop Python plugins into ~/.devmind/plugins/ to add new tools
"""
    console.print(Panel(help_text.strip(), border_style="dim", title="[dim]Help[/dim]"))


def smart_truncate_history(history, max_messages=None, summary_threshold=None):
    """Keep conversation history manageable by summarizing old messages."""
    max_msgs = max_messages or config.history.max_messages
    threshold = summary_threshold or config.history.summary_threshold

    if len(history) <= threshold:
        return history

    old_messages = history[:len(history) - max_msgs + 2]
    recent_messages = history[len(history) - max_msgs + 2:]

    summary_parts = []
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
        f"History truncated: {len(history)} -> {len(summarized) + len(recent_messages)} messages"
    )
    return summarized + recent_messages


def _cmd_cost():
    from cost_tracker import format_cost_summary
    console.print(Panel(
        format_cost_summary(),
        title="[dim]Session Cost[/dim]",
        border_style="dim",
    ))


def _cmd_metrics():
    from metrics import format_metrics_summary
    console.print(Panel(
        format_metrics_summary(),
        title="[dim]Performance Metrics[/dim]",
        border_style="dim",
    ))


def _cmd_tasks(agent):
    console.print(Panel(
        agent.get_task_summary(),
        title="[dim]Task History[/dim]",
        border_style="dim",
    ))


def _cmd_history(history):
    if not history:
        console.print("[dim]Conversation history is empty.[/dim]")
        return
    for i, msg in enumerate(history, 1):
        role = msg["role"].capitalize()
        preview = msg["content"][:200].replace("\n", " ")
        style = "cyan" if msg["role"] == "user" else "green"
        console.print(f"[{style}]{i:2d}. {role}:[/{style}] {preview}")


def _cmd_save(args, history, agent):
    if not args:
        console.print("[red]Usage: /save <name>[/red]")
        return
    try:
        from persistence import save_session
        path = save_session(args, history, agent.model_name)
        console.print(f"[green]Saved:[/green] {path}")
    except Exception as e:
        console.print(f"[red]Save failed:[/red] {e}")


def _cmd_load(args, history):
    if not args:
        console.print("[red]Usage: /load <name>[/red]")
        return history
    try:
        from persistence import load_session
        session = load_session(args)
        console.print(
            f"[green]Loaded[/green] '{session.session_id}' "
            f"- {len(session.history)} messages (model {session.model})"
        )
        return list(session.history)
    except Exception as e:
        console.print(f"[red]Load failed:[/red] {e}")
        return history


def _cmd_sessions():
    try:
        from persistence import list_sessions
        sessions = list_sessions()
    except Exception as e:
        console.print(f"[red]Failed to list sessions:[/red] {e}")
        return

    if not sessions:
        console.print("[dim]No saved sessions.[/dim]")
        return

    table = Table(title="Saved sessions", show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Messages", justify="right")
    table.add_column("Model")
    table.add_column("Updated")
    for s in sessions:
        table.add_row(s["name"], str(s["messages"]), s["model"], s["updated_at"])
    console.print(table)


def _cmd_delete(args):
    if not args:
        console.print("[red]Usage: /delete <name>[/red]")
        return
    try:
        from persistence import delete_session
        if delete_session(args):
            console.print(f"[green]Deleted session '{args}'[/green]")
        else:
            console.print(f"[yellow]Session '{args}' not found[/yellow]")
    except Exception as e:
        console.print(f"[red]Delete failed:[/red] {e}")


def handle_slash_command(cmd, history, agent):
    """Handle a slash command. Returns (should_continue, updated_history)."""
    cmd = cmd.strip()
    lower = cmd.lower()

    parts = cmd.split(maxsplit=1)
    verb = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if verb in ("/exit", "/quit"):
        console.print("\n[dim]Shutting down DevMind... Goodbye![/dim]\n")
        return False, history

    if verb == "/help":
        show_help()
    elif verb == "/cost":
        _cmd_cost()
    elif verb == "/metrics":
        _cmd_metrics()
    elif verb == "/tasks":
        _cmd_tasks(agent)
    elif verb == "/history":
        _cmd_history(history)
    elif verb == "/save":
        _cmd_save(args, history, agent)
    elif verb == "/load":
        history = _cmd_load(args, history)
    elif verb == "/sessions":
        _cmd_sessions()
    elif verb == "/delete":
        _cmd_delete(args)
    elif verb == "/clear":
        history.clear()
        console.clear()
        show_banner()
        console.print("[dim]Chat history cleared.[/dim]\n")
    elif verb == "/cd":
        new_dir = args.strip()
        if not new_dir:
            console.print("[red]Usage: /cd <path>[/red]")
        else:
            try:
                os.chdir(new_dir)
                from context import build_system_prompt
                agent.system_prompt = build_system_prompt()
                console.print(f"[dim]Working directory: {os.getcwd()}[/dim]")
                log.info(f"Working directory changed: {os.getcwd()}")
            except FileNotFoundError:
                console.print(f"[red]Directory not found: {new_dir}[/red]")
    else:
        console.print(f"[red]Unknown command: {lower}[/red] - [dim]type /help[/dim]")

    return True, history


def display_streaming_response(agent, user_input, lc_history):
    """Stream Claude's response token by token to the terminal."""
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

        console.print()

    except Exception as e:
        log.error(f"Streaming display error: {e}")
        if not full_response:
            try:
                full_response = agent.chat(user_input, lc_history)
                try:
                    console.print(Markdown(full_response))
                except Exception:
                    console.print(full_response)
            except Exception as inner:
                console.print(f"[red]Error: {inner}[/red]")

    console.print()
    return full_response


def _maybe_autosave(history, agent, turn):
    if not config.persistence.enabled:
        return
    every = config.persistence.autosave_every
    if every <= 0 or turn % every != 0:
        return
    try:
        from persistence import save_session
        save_session("autosave", history, agent.model_name, metadata={"auto": True})
        log.debug(f"Autosaved at turn {turn}")
    except Exception as e:
        log.debug(f"Autosave skipped: {e}")


def run_repl():
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

    conversation_history = []
    turn = 0

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
            turn += 1

            conversation_history = smart_truncate_history(conversation_history)
            _maybe_autosave(conversation_history, agent, turn)

        except KeyboardInterrupt:
            console.print("\n\n[dim]Ctrl+C detected - shutting down...[/dim]")
            break
        except EOFError:
            break
        except Exception as e:
            log.error(f"REPL error: {e}")
            console.print(f"\n[red]Error: {e}[/red]\n")
            continue


def main():
    """Start DevMind."""
    show_banner()
    run_repl()


if __name__ == "__main__":
    main()
