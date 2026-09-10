"""Axiom CLI: TUI launcher, one-shot tasks, doctor, models, providers."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from axiom.config.config import Config
from axiom.core.logging import setup_logging
from axiom.models.manager import ModelManager


@click.command()
@click.argument("task", required=False)
@click.option("--plan", is_flag=True, help="Run task in PLAN mode (no changes).")
@click.option("--review", is_flag=True, help="Review the current diff.")
@click.option("--agent", "agent_role", default=None, help="Agent role to use.")
@click.option("--model", default=None, help="Model id to use.")
@click.option("--provider", default=None, help="Provider name.")
@click.option("--doctor", "run_doctor_flag", is_flag=True, help="Run diagnostics.")
@click.option("--models", "show_models", is_flag=True, help="List providers and models.")
@click.option("--version", is_flag=True, help="Show version.")
def main(
    task: str | None,
    plan: bool,
    review: bool,
    agent_role: str | None,
    model: str | None,
    provider: str | None,
    run_doctor_flag: bool,
    show_models: bool,
    version: bool,
) -> None:
    """Axiom — terminal-first AI coding agent."""
    setup_logging(quiet_console=True)

    # Force UTF-8 on stdout/stderr (Windows codepage breaks Unicode glyphs).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    if version:
        from axiom import __version__

        click.echo(f"axiom {__version__}")
        return


        click.echo(f"axiom {__version__}")
        return
    if run_doctor_flag:
        from axiom.doctor import run_doctor

        report = asyncio.run(run_doctor())
        click.echo(report.render())
        sys.exit(0 if report.passed == report.total else 1)
    if show_models:
        _print_models(Config())
        return

    if task or plan or review:
        _run_oneshot(task or "", plan=plan, review=review, model=model,
                     provider=provider, role=agent_role)
        return

    # Default: launch TUI
    from axiom.terminal.app import run_tui

    run_tui()


def _print_models(config: Config) -> None:
    manager = ModelManager(config.to_dict())
    click.echo("PROVIDERS")
    for info in manager.list_providers():
        click.echo(f"{info.display_name:<20} {'✓' if info else '✗'}")
    click.echo("")
    click.echo("MODELS")
    for model_info in manager.list_models():
        caps = []
        if model_info.reasoning:
            caps.append("reasoning")
        if model_info.vision:
            caps.append("vision")
        suffix = f" ({', '.join(caps)})" if caps else ""
        click.echo(f"{model_info.id}{suffix}")


def _run_oneshot(
    task: str, plan: bool = False, review: bool = False,
    model: str | None = None, provider: str | None = None, role: str | None = None,
) -> None:
    """Run a single task headlessly and print the result."""
    from axiom.agent.agent import Agent
    from axiom.config.config import Config

    config = Config()
    if model:
        config.set("model", "model", value=model)
    if provider:
        config.set("model", "provider", value=provider)

    manager = ModelManager(config.to_dict())
    current = manager.get_current_model()
    model_id = model or (current.id if current else "GPT-OSS-120B")
    provider_name = provider or config.get("model", "provider", default="openai_compatible")
    api_key = config.get_api_key(provider_name)
    if provider_name != "ollama" and not api_key:
        click.echo("ERROR: no API key. Set AXIOM_API_KEY or use --provider ollama.")
        sys.exit(1)
    try:
        model_provider = manager.create_provider(provider_name, model=model_id, api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: cannot create provider: {exc}")
        sys.exit(1)

    if review and not task:
        task = "Review the current git diff and report issues with severity levels."

    mode = "PLAN" if plan else "BUILD"
    agent = Agent(workspace=Path.cwd(), config=config.to_dict(), provider=model_provider)
    result = asyncio.run(agent.run_task(task, mode=mode))
    if result.final_text:
        click.echo(result.final_text)
    if result.error:
        click.echo(f"[{result.status.value}] {result.error}")
    if not result.final_text and not result.error:
        click.echo(f"[{result.status.value}] no output")
    sys.exit(0 if result.status.value in ("complete", "cancelled") else 2)


if __name__ == "__main__":
    main()
