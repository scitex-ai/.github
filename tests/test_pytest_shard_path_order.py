"""Regression coverage for pytest shard membership and emitted path order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

_WORKFLOW = Path(__file__).parents[1] / ".github/workflows/pytest-matrix.yml"


def _shard_builder() -> str:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["pytest-matrix"]["steps"]
    run = next(step["run"] for step in steps if "TEST_FILES" in step.get("run", ""))
    invocation = run[run.index("mapfile -t TEST_FILES") :]
    return invocation.split("<<'PY'\n", 1)[1].split("\nPY\n)", 1)[0]


def _write_test_file(path: Path, test_count: int, *, fixture: bool = False) -> None:
    argument = "nested_fixture" if fixture else ""
    lines = [f"def test_{number}({argument}): assert True" for number in range(test_count)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fixture_tree(root: Path) -> None:
    nested = root / "tests" / "nested"
    nested.mkdir(parents=True)
    (nested / "conftest.py").write_text(
        "import pytest\n\n@pytest.fixture\ndef nested_fixture(): return 42\n",
        encoding="utf-8",
    )
    _write_test_file(nested / "test_a.py", 4, fixture=True)
    _write_test_file(root / "tests" / "test_b.py", 3)
    _write_test_file(nested / "test_c.py", 2, fixture=True)
    _write_test_file(root / "tests" / "test_d.py", 1)


def _run_builder(root: Path, index: int, count: int) -> list[str]:
    completed = subprocess.run(
        [sys.executable, "-c", _shard_builder(), str(index), str(count)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.splitlines()


def test_shard_builder_preserves_weight_balanced_membership(tmp_path: Path) -> None:
    # Arrange
    _fixture_tree(tmp_path)
    expected = [
        {"tests/nested/test_a.py", "tests/test_d.py"},
        {"tests/nested/test_c.py", "tests/test_b.py"},
    ]
    # Act
    actual = [set(_run_builder(tmp_path, index, 2)) for index in range(2)]
    # Assert
    assert actual == expected


def test_shard_builder_emits_paths_in_lexical_order(tmp_path: Path) -> None:
    # Arrange
    _fixture_tree(tmp_path)
    # Act
    emitted = _run_builder(tmp_path, 0, 1)
    # Assert
    assert emitted == sorted(emitted)


def test_emitted_order_preserves_nested_conftest_fixture(tmp_path: Path) -> None:
    # Arrange
    _fixture_tree(tmp_path)
    emitted = _run_builder(tmp_path, 0, 1)
    # Act
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *emitted],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    # Assert
    assert completed.returncode == 0, completed.stdout + completed.stderr
