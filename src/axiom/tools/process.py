"""Background process manager: start/stop/read long-running processes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from axiom.core.logging import get_logger
from axiom.tools.terminal import resolve_shell

logger = get_logger("process")


@dataclass
class ManagedProcess:
    """A long-running (background) process owned by Axiom."""

    id: str
    command: str
    cwd: str
    pid: int | None = None
    status: str = "RUNNING"
    exit_code: int | None = None
    stdout: list[str] = field(default_factory=list)
    stderr: list[str] = field(default_factory=list)
    _proc: asyncio.subprocess.Process | None = None

    def get_output(self, tail: int = 100) -> str:
        lines = self.stdout[-tail:]
        errors = self.stderr[-tail // 2:]
        out = "\n".join(lines)
        if errors:
            out += "\n[stderr]\n" + "\n".join(errors)
        return out

    def describe(self) -> str:
        exit_info = f"  EXIT: {self.exit_code}\n" if self.exit_code is not None else ""
        return (
            f"PROCESS {self.id}\n{self.command}\n"
            f"PID: {self.pid}\nSTATUS: {self.status}\n{exit_info}"
        )


class ProcessManager:
    """Manages background processes started by tools."""

    def __init__(self) -> None:
        self._processes: dict[str, ManagedProcess] = {}
        self._counter = 0

    def list_processes(self) -> list[ManagedProcess]:
        return list(self._processes.values())

    def get(self, process_id: str) -> ManagedProcess | None:
        return self._processes.get(process_id)

    async def start(
        self, command: str, cwd: str, shell: str | None = None
    ) -> ManagedProcess:
        self._counter += 1
        proc_id = f"#{self._counter:02d}"
        program, _flag = resolve_shell(shell)
        if program.endswith(("powershell.exe", "pwsh.exe")):
            argv = [program, "-NoProfile", "-NonInteractive", "-Command", command]
        elif program == "cmd.exe":
            argv = [program, "/c", command]
        else:
            argv = [program, "-c", command]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        managed = ManagedProcess(id=proc_id, command=command, cwd=cwd, pid=proc.pid, _proc=proc)
        self._processes[proc_id] = managed
        asyncio.get_running_loop().create_task(self._pump(managed))
        logger.info("Started process %s: %s", proc_id, command)
        return managed

    async def _pump(self, managed: ManagedProcess) -> None:
        proc = managed._proc
        if proc is None or proc.stdout is None or proc.stderr is None:
            return
        async def read_stream(stream: asyncio.StreamReader, sink: list[str]) -> None:
            while True:
                line = await stream.readline()
                if not line:
                    break
                sink.append(line.decode("utf-8", "replace").rstrip())

        await asyncio.gather(
            read_stream(proc.stdout, managed.stdout),
            read_stream(proc.stderr, managed.stderr),
        )
        managed.exit_code = await proc.wait()
        managed.status = "EXITED"

    async def stop(self, process_id: str) -> bool:
        managed = self._processes.get(process_id)
        if managed is None or managed._proc is None:
            return False
        try:
            managed._proc.kill()
        except ProcessLookupError:
            pass
        managed.status = "STOPPED"
        return True

    def status_report(self) -> str:
        if not self._processes:
            return "No background processes."
        return "\n\n".join(p.describe() for p in self._processes.values())
