"""TrajectoryStore — персист запусков: save/resume/list (п.10)."""
from __future__ import annotations

from pathlib import Path

from axiom.core.config import axiom_home
from axiom.core.trajectory import Trajectory


class TrajectoryStore:
    def __init__(self, directory: Path | None = None) -> None:
        self._dir = directory or (axiom_home() / "trajectories")

    @property
    def directory(self) -> Path:
        return self._dir

    def _path(self, run_id: str) -> Path:
        safe = "".join(c for c in run_id if c.isalnum() or c in "-_")
        if not safe:
            raise ValueError("Invalid run id")
        return self._dir / f"{safe}.jsonl"

    def save(self, trajectory: Trajectory) -> Path:
        path = self._path(trajectory.run_id)
        trajectory.save(path)
        return path

    def load(self, run_id: str) -> Trajectory | None:
        path = self._path(run_id)
        if not path.exists():
            return None
        try:
            return Trajectory.load(path)
        except Exception:
            return None

    def resume(self, run_id: str) -> Trajectory | None:
        """Resume run: продолжить с последнего состояния (тот же run_id)."""
        loaded = self.load(run_id)
        if loaded is None:
            return None
        loaded.append("trajectory.resume", f"resumed {run_id}")
        return loaded

    def list_runs(self) -> list[dict]:
        if not self._dir.exists():
            return []
        out: list[dict] = []
        for path in sorted(self._dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
            out.append({"run_id": path.stem, "path": str(path), "size": path.stat().st_size})
        return out
