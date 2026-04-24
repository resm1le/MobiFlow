from __future__ import annotations

import importlib
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import model_validator

from mobiflow_agent.common.contracts import StrictModel


class RuntimeCheckpointMode(str, Enum):
    MEMORY = "memory"
    SQLITE = "sqlite"


class RuntimeCheckpointConfig(StrictModel):
    mode: RuntimeCheckpointMode
    sqlite_path: str | None = None

    @model_validator(mode="after")
    def validate_config(self) -> "RuntimeCheckpointConfig":
        if self.mode == RuntimeCheckpointMode.SQLITE and not self.sqlite_path:
            raise ValueError("RuntimeCheckpointConfig requires sqlite_path when mode is sqlite.")
        return self


def create_checkpointer(config: RuntimeCheckpointConfig) -> Any:
    serializer = _create_serializer()
    if config.mode == RuntimeCheckpointMode.MEMORY:
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver(serde=serializer)

    sqlite_path = config.sqlite_path
    if not sqlite_path:
        raise ValueError("create_checkpointer() requires sqlite_path when mode is sqlite.")

    try:
        sqlite_module = importlib.import_module("langgraph.checkpoint.sqlite")
    except ModuleNotFoundError as exc:
        raise ValueError(
            "SQLite checkpointing requires the optional dependency 'langgraph-checkpoint-sqlite'."
        ) from exc

    path = Path(sqlite_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    return sqlite_module.SqliteSaver(connection, serde=serializer)


def _create_serializer() -> Any:
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    return JsonPlusSerializer(pickle_fallback=True)
