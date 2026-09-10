"""Doctor: environment and configuration diagnostics."""

from __future__ import annotations

import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Any

from axiom.config.config import Config, global_config_dir
from axiom.core.logging import get_logger
from axiom.models.manager import ModelManager
from axiom.models.ollama import OllamaProvider
from axiom.tools.git import git_available

logger = get_logger("doctor")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    warning: bool = False  # ok-ish but worth noting


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.ok)

    @property
    def total(self) -> int:
        return len(self.checks)

    def render(self) -> str:
        lines = ["AXIOM DOCTOR", ""]
        for check in self.checks:
            mark = "✓" if check.ok else ("⚠" if check.warning else "✗")
            detail = f" — {check.detail}" if check.detail else ""
            lines.append(f"{mark} {check.name}{detail}")
        warnings = [c.name for c in self.checks if c.ok and c.warning]
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in warnings:
                lines.append(f"⚠ {w}")
        lines.append("")
        lines.append(f"Result: {self.passed}/{self.total} OK")
        return "\n".join(lines)


async def run_doctor(workspace: Any = None) -> DoctorReport:
    """Run all diagnostics and return a report."""
    report = DoctorReport()
    config = Config(workspace=workspace)

    # Python version
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    report.checks.append(Check("Python", sys.version_info >= (3, 11), version))

    # Configuration
    try:
        config.get("model", "model")
        report.checks.append(Check("Configuration", True, f"config dir: {global_config_dir()}"))
    except Exception as exc:  # noqa: BLE001
        report.checks.append(Check("Configuration", False, str(exc)))

    # API key (warning when missing — Ollama works without)
    manager = ModelManager(config.to_dict())
    api_key = config.get_api_key()
    report.checks.append(
        Check("API key", True, "set" if api_key else "not set (Ollama-only mode)",
              warning=not api_key)
    )

    # Primary model availability via provider
    try:
        health = await manager.check_provider_health(config.get("model", "provider", default="openai_compatible"))
        ok = health == "healthy"
        report.checks.append(Check("Model provider", ok, health, warning=not ok))
    except Exception as exc:  # noqa: BLE001
        report.checks.append(Check("Model provider", False, str(exc)))

    # Ollama
    ollama = OllamaProvider()
    models = await ollama.list_models()
    report.checks.append(
        Check("Ollama", bool(models), f"{len(models)} models" if models else "unavailable",
              warning=not models)
    )

    # Tools
    from axiom.tools.filesystem import read_file
    report.checks.append(Check("Tool registry", callable(read_file)))

    # Permissions
    from axiom.permissions.manager import PermissionManager
    pm = PermissionManager()
    report.checks.append(Check("Permissions", pm.get_permission_state("x.y") is not None))

    # Workspace
    ws = workspace or __import__("pathlib").Path.cwd()
    report.checks.append(Check("Workspace", ws.exists(), str(ws)))

    # Git
    report.checks.append(Check("Git", git_available(),
                               "available" if git_available() else "git not found"))

    # Sessions / SQLite
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT 1")
        conn.close()
        report.checks.append(Check("Sessions (SQLite)", True))
    except sqlite3.Error as exc:
        report.checks.append(Check("Sessions (SQLite)", False, str(exc)))

    # Dependencies
    missing = []
    for module in ("httpx", "pydantic", "rich", "textual", "click"):
        try:
            __import__(module)
        except ImportError:
            missing.append(module)
    report.checks.append(Check("Dependencies", not missing,
                               "all present" if not missing else f"missing: {', '.join(missing)}"))

    return report
