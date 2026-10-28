import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from agentic.store import SQLiteAnalytics, seed


@pytest.fixture
def database(tmp_path):
    seed(tmp_path / "demo.sqlite")
    return SQLiteAnalytics(tmp_path / "demo.sqlite")
