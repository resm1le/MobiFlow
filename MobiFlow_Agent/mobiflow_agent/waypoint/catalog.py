from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Callable

from pydantic import Field, ValidationError

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.waypoint.models import WaypointSequence


SEQUENCE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\.v[1-9][0-9]*$"
)


class SequenceSummary(StrictModel):
    sequence_id: str = Field(min_length=1)
    behavior_label: str = Field(min_length=1)
    profile_package: str = Field(min_length=1)
    waypoint_ids: list[str] = Field(default_factory=list)


class SequenceCatalogError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        sequence_id: str | None = None,
        source: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.sequence_id = sequence_id
        self.source = source


class SequenceCatalog:
    def __init__(self, sequences: dict[str, WaypointSequence]) -> None:
        self._sequences = {
            sequence_id: sequence.model_copy(deep=True)
            for sequence_id, sequence in sequences.items()
        }

    @classmethod
    def from_directory(cls, directory: Path) -> "SequenceCatalog":
        if not directory.is_dir():
            raise SequenceCatalogError(
                "SEQUENCE_CATALOG_NOT_FOUND",
                f"Sequence catalog directory does not exist: {directory}",
                source=str(directory),
            )
        sources = [
            (str(path), lambda path=path: path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"), key=lambda item: item.name)
        ]
        return cls._from_sources(sources)

    @classmethod
    def default(cls) -> "SequenceCatalog":
        directory = resources.files("mobiflow_agent.waypoint").joinpath("sequences")
        if not directory.is_dir():
            raise SequenceCatalogError(
                "SEQUENCE_CATALOG_NOT_FOUND",
                "Packaged sequence catalog is not available.",
                source=str(directory),
            )
        entries = sorted(
            (
                entry
                for entry in directory.iterdir()
                if entry.is_file() and entry.name.endswith(".json")
            ),
            key=lambda entry: entry.name,
        )
        sources = [
            (str(entry), lambda entry=entry: entry.read_text(encoding="utf-8"))
            for entry in entries
        ]
        return cls._from_sources(sources)

    @classmethod
    def _from_sources(
        cls,
        sources: list[tuple[str, Callable[[], str]]],
    ) -> "SequenceCatalog":
        sequences: dict[str, WaypointSequence] = {}
        for source, read_text in sources:
            try:
                raw_definition = json.loads(read_text())
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise SequenceCatalogError(
                    "SEQUENCE_SOURCE_INVALID_JSON",
                    f"Could not read sequence definition as JSON: {source}",
                    source=source,
                ) from exc
            if not isinstance(raw_definition, dict):
                raise SequenceCatalogError(
                    "SEQUENCE_DEFINITION_INVALID",
                    f"Sequence definition must be a JSON object: {source}",
                    source=source,
                )
            try:
                sequence = WaypointSequence.model_validate(raw_definition)
            except ValidationError as exc:
                raise SequenceCatalogError(
                    "SEQUENCE_DEFINITION_INVALID",
                    f"Sequence definition does not match the Agent contract: {source}",
                    sequence_id=_candidate_sequence_id(raw_definition),
                    source=source,
                ) from exc
            _require_versioned_sequence_id(sequence.sequence_id, source=source)
            if sequence.sequence_id in sequences:
                raise SequenceCatalogError(
                    "SEQUENCE_ID_DUPLICATE",
                    f"Duplicate sequence id: {sequence.sequence_id}",
                    sequence_id=sequence.sequence_id,
                    source=source,
                )
            sequences[sequence.sequence_id] = sequence
        return cls(sequences)

    def list_sequences(self) -> list[SequenceSummary]:
        return [
            SequenceSummary(
                sequence_id=sequence.sequence_id,
                behavior_label=sequence.behavior_label,
                profile_package=sequence.profile_package,
                waypoint_ids=[waypoint.waypoint_id for waypoint in sequence.waypoints],
            )
            for sequence in (
                self._sequences[sequence_id]
                for sequence_id in sorted(self._sequences)
            )
        ]

    def resolve_sequence(self, sequence_id: str) -> WaypointSequence:
        _require_versioned_sequence_id(sequence_id)
        try:
            sequence = self._sequences[sequence_id]
        except KeyError as exc:
            raise SequenceCatalogError(
                "SEQUENCE_NOT_FOUND",
                f"Sequence id is not registered: {sequence_id}",
                sequence_id=sequence_id,
            ) from exc
        return sequence.model_copy(deep=True)


def _candidate_sequence_id(definition: dict) -> str | None:
    value = definition.get("sequence_id")
    return value if isinstance(value, str) else None


def _require_versioned_sequence_id(sequence_id: str, *, source: str | None = None) -> None:
    if SEQUENCE_ID_PATTERN.fullmatch(sequence_id):
        return
    raise SequenceCatalogError(
        "SEQUENCE_ID_INVALID",
        f"Sequence id must be a lowercase, explicit .vN identifier: {sequence_id}",
        sequence_id=sequence_id,
        source=source,
    )


__all__ = [
    "SEQUENCE_ID_PATTERN",
    "SequenceCatalog",
    "SequenceCatalogError",
    "SequenceSummary",
]
