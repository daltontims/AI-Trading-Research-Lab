import pytest


@pytest.fixture(autouse=True)
def isolated_lake(tmp_path, monkeypatch):
    """Every test gets its own empty data lake."""
    monkeypatch.setenv("LAB_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"
