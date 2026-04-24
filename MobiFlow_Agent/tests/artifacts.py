from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def artifact_dir(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def sqlite_path(tmp_path: Path, name: str) -> Path:
    return artifact_dir(tmp_path, "sqlite") / f"{name}-{uuid4().hex}.sqlite"
