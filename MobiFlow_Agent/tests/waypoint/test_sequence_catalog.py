from __future__ import annotations

import json
from pathlib import Path

import pytest

from mobiflow_agent.waypoint.catalog import SequenceCatalog, SequenceCatalogError


def _sequence_payload(sequence_id: str, *, waypoint_id: str = "arrived") -> dict:
    return {
        "sequence_id": sequence_id,
        "behavior_label": sequence_id.removesuffix(".v1").replace(".", "_"),
        "profile_package": "com.example.app",
        "waypoints": [
            {
                "waypoint_id": waypoint_id,
                "description": f"Reach {waypoint_id}.",
                "arrival_spec": {
                    "verification_id": f"verify:{waypoint_id}",
                    "target_kind": "task",
                    "target_id": waypoint_id,
                    "success_checks": [
                        {
                            "check_id": f"{waypoint_id}-visible",
                            "description": f"{waypoint_id} is visible.",
                        }
                    ],
                },
            }
        ],
    }


def _write_sequence(directory: Path, filename: str, sequence_id: str) -> None:
    (directory / filename).write_text(
        json.dumps(_sequence_payload(sequence_id)),
        encoding="utf-8",
    )


def test_catalog_lists_sequences_in_id_order_and_resolves_typed_models(tmp_path: Path) -> None:
    _write_sequence(tmp_path, "second.json", "sample.second.v1")
    _write_sequence(tmp_path, "first.json", "sample.first.v1")

    catalog = SequenceCatalog.from_directory(tmp_path)

    assert [item.sequence_id for item in catalog.list_sequences()] == [
        "sample.first.v1",
        "sample.second.v1",
    ]
    resolved = catalog.resolve_sequence("sample.first.v1")
    assert resolved.sequence_id == "sample.first.v1"
    assert resolved.waypoints[0].waypoint_id == "arrived"


def test_catalog_resolve_results_are_deeply_isolated(tmp_path: Path) -> None:
    _write_sequence(tmp_path, "sequence.json", "sample.mutable.v1")
    catalog = SequenceCatalog.from_directory(tmp_path)

    first = catalog.resolve_sequence("sample.mutable.v1")
    second = catalog.resolve_sequence("sample.mutable.v1")
    first.waypoints[0].allowed_actions.append("mobile.first_only")
    first.waypoints.clear()

    third = catalog.resolve_sequence("sample.mutable.v1")
    assert first is not second
    assert second.waypoints is not third.waypoints
    assert [waypoint.waypoint_id for waypoint in third.waypoints] == ["arrived"]
    assert "mobile.first_only" not in third.waypoints[0].allowed_actions


def test_catalog_unknown_sequence_has_structured_error(tmp_path: Path) -> None:
    catalog = SequenceCatalog.from_directory(tmp_path)

    with pytest.raises(SequenceCatalogError) as exc_info:
        catalog.resolve_sequence("sample.missing.v1")

    assert exc_info.value.code == "SEQUENCE_NOT_FOUND"
    assert exc_info.value.sequence_id == "sample.missing.v1"
    assert "sample.missing.v1" in exc_info.value.message


def test_catalog_rejects_invalid_requested_sequence_id(tmp_path: Path) -> None:
    catalog = SequenceCatalog.from_directory(tmp_path)

    with pytest.raises(SequenceCatalogError) as exc_info:
        catalog.resolve_sequence("sample.latest")

    assert exc_info.value.code == "SEQUENCE_ID_INVALID"
    assert exc_info.value.sequence_id == "sample.latest"


def test_catalog_rejects_invalid_json(tmp_path: Path) -> None:
    source = tmp_path / "broken.json"
    source.write_text("{not-json", encoding="utf-8")

    with pytest.raises(SequenceCatalogError) as exc_info:
        SequenceCatalog.from_directory(tmp_path)

    assert exc_info.value.code == "SEQUENCE_SOURCE_INVALID_JSON"
    assert exc_info.value.source == str(source)


def test_catalog_rejects_invalid_sequence_definition(tmp_path: Path) -> None:
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps({"sequence_id": "sample.invalid.v1"}), encoding="utf-8")

    with pytest.raises(SequenceCatalogError) as exc_info:
        SequenceCatalog.from_directory(tmp_path)

    assert exc_info.value.code == "SEQUENCE_DEFINITION_INVALID"
    assert exc_info.value.source == str(source)


def test_catalog_rejects_unversioned_sequence_id(tmp_path: Path) -> None:
    _write_sequence(tmp_path, "invalid-id.json", "sample.sequence")

    with pytest.raises(SequenceCatalogError) as exc_info:
        SequenceCatalog.from_directory(tmp_path)

    assert exc_info.value.code == "SEQUENCE_ID_INVALID"
    assert exc_info.value.sequence_id == "sample.sequence"


def test_catalog_rejects_duplicate_sequence_ids(tmp_path: Path) -> None:
    _write_sequence(tmp_path, "first.json", "sample.duplicate.v1")
    _write_sequence(tmp_path, "second.json", "sample.duplicate.v1")

    with pytest.raises(SequenceCatalogError) as exc_info:
        SequenceCatalog.from_directory(tmp_path)

    assert exc_info.value.code == "SEQUENCE_ID_DUPLICATE"
    assert exc_info.value.sequence_id == "sample.duplicate.v1"


def test_bad_source_prevents_partial_catalog_construction(tmp_path: Path) -> None:
    _write_sequence(tmp_path, "first.json", "sample.valid.v1")
    (tmp_path / "second.json").write_text("[]", encoding="utf-8")

    with pytest.raises(SequenceCatalogError) as exc_info:
        SequenceCatalog.from_directory(tmp_path)

    assert exc_info.value.code == "SEQUENCE_DEFINITION_INVALID"


def test_empty_directory_builds_empty_catalog(tmp_path: Path) -> None:
    catalog = SequenceCatalog.from_directory(tmp_path)

    assert catalog.list_sequences() == []


def test_missing_directory_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(SequenceCatalogError) as exc_info:
        SequenceCatalog.from_directory(missing)

    assert exc_info.value.code == "SEQUENCE_CATALOG_NOT_FOUND"
    assert exc_info.value.source == str(missing)
