from __future__ import annotations

import shutil
import gc
from pathlib import Path
from uuid import uuid4

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = PROJECT_ROOT / ".test-artifacts"


@pytest.fixture
def artifact_tmp_path(request) -> Path:
    path = ARTIFACT_ROOT / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)

    def cleanup() -> None:
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
        gc.collect()
        shutil.rmtree(path, ignore_errors=True)
        try:
            ARTIFACT_ROOT.rmdir()
        except OSError:
            pass

    request.addfinalizer(cleanup)
    return path
