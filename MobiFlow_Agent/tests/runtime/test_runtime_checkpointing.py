from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from mobiflow_agent.runtime.checkpointing import (
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    create_checkpointer,
)
from tests.artifacts import sqlite_path


def _sqlite_test_path(artifact_tmp_path: Path, name: str) -> Path:
    return sqlite_path(artifact_tmp_path, name)


def test_create_checkpointer_memory_returns_memory_saver() -> None:
    saver = create_checkpointer(RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.MEMORY))

    assert saver.__class__.__name__ in {"MemorySaver", "InMemorySaver"}


def test_create_checkpointer_sqlite_requires_sqlite_path() -> None:
    with pytest.raises(ValueError, match="sqlite_path"):
        create_checkpointer(RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.SQLITE, sqlite_path=None))


def test_create_checkpointer_sqlite_returns_sqlite_saver(artifact_tmp_path: Path) -> None:
    saver = create_checkpointer(
        RuntimeCheckpointConfig(
            mode=RuntimeCheckpointMode.SQLITE,
            sqlite_path=str(_sqlite_test_path(artifact_tmp_path, "runtime")),
        )
    )

    assert saver.__class__.__name__ == "SqliteSaver"
    saver.conn.close()


def test_create_checkpointer_sqlite_raises_clear_error_when_dependency_missing(monkeypatch, artifact_tmp_path: Path) -> None:
    original_import_module = importlib.import_module

    def _broken_import(name: str, package: str | None = None):
        if name == "langgraph.checkpoint.sqlite":
            raise ModuleNotFoundError("missing sqlite saver")
        return original_import_module(name, package)

    monkeypatch.setattr("mobiflow_agent.runtime.checkpointing.importlib.import_module", _broken_import)

    with pytest.raises(ValueError, match="langgraph-checkpoint-sqlite"):
        create_checkpointer(
            RuntimeCheckpointConfig(
                mode=RuntimeCheckpointMode.SQLITE,
                sqlite_path=str(_sqlite_test_path(artifact_tmp_path, "runtime-missing-dep")),
            )
        )

