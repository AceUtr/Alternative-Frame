from pathlib import Path

import pytest


REQUIRED_HEADINGS = {
    "# 需求与验收条件",
    "## 1. 任务概述",
    "## 2. 功能需求",
    "## 3. 非功能需求与约束",
    "## 4. 验收检查清单",
    "## 5. 完成定义",
    "## 6. 已知风险与假设",
}
REQUIRED_CONTRACT_TERMS = {
    "requirements.md",
    "requirements_written",
    "file_exists",
    "file_editor",
    "最大重试次数为 2",
}


def assert_requirements_deliverable(workspace: Path) -> None:
    deliverable = workspace / "requirements.md"
    assert deliverable.is_file(), "requirements.md must exist at the workspace root"

    content = deliverable.read_text(encoding="utf-8")
    headings = {line.strip() for line in content.splitlines() if line.startswith("#")}
    missing_headings = REQUIRED_HEADINGS - headings
    assert not missing_headings, f"missing required sections: {sorted(missing_headings)}"

    missing_terms = {term for term in REQUIRED_CONTRACT_TERMS if term not in content}
    assert not missing_terms, f"missing task-contract details: {sorted(missing_terms)}"


def test_repository_requirements_meets_acceptance_criteria() -> None:
    workspace = Path(__file__).resolve().parents[1]

    assert_requirements_deliverable(workspace)


def test_requirements_in_a_nested_directory_does_not_satisfy_exact_path(tmp_path: Path) -> None:
    nested = tmp_path / "docs"
    nested.mkdir()
    (nested / "requirements.md").write_text("misplaced", encoding="utf-8")

    with pytest.raises(AssertionError, match="workspace root"):
        assert_requirements_deliverable(tmp_path)


def test_requirements_with_incomplete_content_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "requirements.md").write_text("# 需求与验收条件\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="missing required sections"):
        assert_requirements_deliverable(tmp_path)
