import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1]))

from validation.run_demo_stability import _verify_files


def test_verify_files_returns_hashes_for_all_required_artifacts(tmp_path):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("beta", encoding="utf-8")

    hashes = _verify_files(tmp_path, ("a.txt", "b.txt"))

    assert set(hashes) == {"a.txt", "b.txt"}
    assert all(len(value) == 64 for value in hashes.values())


def test_verify_files_rejects_missing_artifact(tmp_path):
    try:
        _verify_files(tmp_path, ("missing.txt",))
    except RuntimeError as exc:
        assert "missing artifacts" in str(exc)
    else:
        raise AssertionError("missing stability evidence must fail closed")

