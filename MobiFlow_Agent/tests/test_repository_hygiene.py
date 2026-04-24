from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ROOT_ARTIFACTS = (
    ".pytest_cache",
    ".test-artifacts",
    "task-harness-test.sqlite3",
)
FORBIDDEN_ROOT_PREFIXES = (
    ".pytest-",
)
FORBIDDEN_ARTIFACT_DIRS = (
    PROJECT_ROOT / "var" / "test-artifacts",
)


def test_repository_root_has_no_test_runtime_artifacts() -> None:
    violations: list[str] = []
    for child in PROJECT_ROOT.iterdir():
        if child.name in FORBIDDEN_ROOT_ARTIFACTS:
            violations.append(str(child.relative_to(PROJECT_ROOT)))
        if any(child.name.startswith(prefix) for prefix in FORBIDDEN_ROOT_PREFIXES):
            violations.append(str(child.relative_to(PROJECT_ROOT)))
    for path in FORBIDDEN_ARTIFACT_DIRS:
        if path.exists():
            violations.append(str(path.relative_to(PROJECT_ROOT)))

    assert violations == []
