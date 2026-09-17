from pathlib import Path
import yaml

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/pytest-matrix.yml"


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def test_reusable_matrix_has_fast_and_full_policy_inputs():
    data = workflow()
    call = data.get("on", data.get(True))["workflow_call"]["inputs"]
    # A single-version ordinary PR is an explicit per-caller optimization.
    # The shared default must continue to emit every context that existing
    # branch protection requires, otherwise a fully-green PR is unmergeable.
    assert call["ordinary_pr_python"]["default"] == ""
    assert call["full_python_versions"]["default"] == '["3.11","3.12","3.13"]'
    matrix = str(data["jobs"]["pytest-matrix"]["strategy"]["matrix"]["python-version"])
    assert "github.base_ref == 'develop'" in matrix
    assert "inputs.ordinary_pr_python != ''" in matrix
    assert "full_python_versions" in matrix


def test_reusable_matrix_uses_dynamic_cpu_and_low_priority():
    job = str(workflow()["jobs"]["pytest-matrix"])
    assert "cpu.max" in job
    assert "sched_getaffinity" in job
    assert "nice -n 10 ionice -c 2 -n 7" in job
    assert "export PYTEST_XDIST_AUTO_NUM_WORKERS" not in job


def test_reusable_matrix_has_stable_fail_closed_aggregate():
    gate = workflow()["jobs"]["pytest-aggregate"]
    assert gate["name"] == "pytest aggregate gate"
    assert gate["needs"] == ["pytest-matrix"]
    assert gate["if"] == "always()"
    assert '!= "success"' in str(gate["steps"])


def test_caller_specific_preparation_contract_is_available():
    data = workflow()
    call = data.get("on", data.get(True))["workflow_call"]["inputs"]
    assert call["pre_test_command"]["default"] == ""
    job = data["jobs"]["pytest-matrix"]
    assert "pre_test_command" in str(job["steps"])
