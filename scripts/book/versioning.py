"""Git-backed change set and proposal bundle helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
import subprocess
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ChangeSet:
    """A reviewable bundle of agent-authored changes."""

    changeset_id: str
    title: str
    agent_id: str
    base_ref: str
    branch_name: str
    files: list[str]
    diff: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class ChangeSetManager:
    """Create durable proposal bundles backed by git diffs."""

    def __init__(self, repo_root: Path | str = Path(".")):
        self.repo_root = Path(repo_root)
        self.bundle_dir = self.repo_root / "proposals" / "changesets"

    def create(
        self,
        title: str,
        agent_id: str,
        files: list[str] | None = None,
        branch_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChangeSet:
        files = files or []
        changeset_id = f"changeset_{uuid4().hex[:12]}"
        base_ref = self._git(["rev-parse", "--short", "HEAD"], default="unknown")
        branch = branch_name or f"codex/{agent_id}/{changeset_id}"
        diff = self._diff(files)
        changeset = ChangeSet(
            changeset_id=changeset_id,
            title=title,
            agent_id=agent_id,
            base_ref=base_ref,
            branch_name=branch,
            files=files,
            diff=diff,
            metadata=metadata or {},
        )
        self._write(changeset)
        return changeset

    def load(self, changeset_id: str) -> ChangeSet:
        path = self.bundle_dir / f"{changeset_id}.json"
        if not path.exists():
            raise KeyError(f"Change set not found: {changeset_id}")
        return ChangeSet(**json.loads(path.read_text()))

    def list(self) -> list[ChangeSet]:
        return [
            ChangeSet(**json.loads(path.read_text()))
            for path in sorted(self.bundle_dir.glob("*.json"))
        ]

    def _write(self, changeset: ChangeSet) -> None:
        self.bundle_dir.mkdir(parents=True, exist_ok=True)
        (self.bundle_dir / f"{changeset.changeset_id}.json").write_text(
            json.dumps(asdict(changeset), indent=2, sort_keys=True) + "\n"
        )
        (self.bundle_dir / f"{changeset.changeset_id}.diff").write_text(changeset.diff)

    def _diff(self, files: list[str]) -> str:
        args = ["diff", "--"]
        args.extend(files)
        return self._git(args, default="")

    def _git(self, args: list[str], default: str = "") -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return default
        if completed.returncode != 0:
            return default
        return completed.stdout.strip()
