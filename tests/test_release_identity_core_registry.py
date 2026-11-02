"""Exact owner lookup and immutable policy data; no publisher registration."""

from dataclasses import replace

import pytest
from _release_core_fixtures import OWNERS, policy

from release_core import DEFAULT_REGISTRY, PolicyRegistry


@pytest.fixture(params=OWNERS, ids=lambda row: row["key"])
def expected_policy(request):
    return policy(request.param)


def test_empty_default_refuses_even_the_real_test_owners(expected_policy):
    # Arrange
    repository = expected_policy.repository
    # Act / Assert
    with pytest.raises(ValueError, match="not registered"):
        DEFAULT_REGISTRY.resolve(repository)


def test_explicit_owner_table_returns_only_its_exact_policy(expected_policy):
    # Arrange
    registry = PolicyRegistry((expected_policy,))
    # Act
    actual = registry.resolve(expected_policy.repository)
    # Assert
    assert actual is expected_policy


def test_prefix_guess_is_not_an_owner_registration(expected_policy):
    # Arrange
    registry = PolicyRegistry((expected_policy,))
    owner, name = expected_policy.repository.split("/")
    another = owner + "/scitex-" + name
    # Act / Assert
    with pytest.raises(ValueError, match="not registered"):
        registry.resolve(another)


def test_duplicate_owner_table_is_refused(expected_policy):
    # Arrange
    supplied = (expected_policy, expected_policy)
    # Act / Assert
    with pytest.raises(ValueError, match="duplicate registered"):
        PolicyRegistry(supplied)


def test_mutable_owner_table_is_not_a_closed_registration(expected_policy):
    # Arrange
    supplied = [expected_policy]
    # Act / Assert
    with pytest.raises(TypeError, match="immutable tuples"):
        PolicyRegistry(supplied)


@pytest.mark.parametrize(
    "field",
    ["required_members", "omitted_paths", "omitted_prefixes", "forbidden_sdist_paths"],
)
def test_mutable_path_selection_is_not_an_immutable_policy(expected_policy, field):
    # Arrange
    supplied = list(getattr(expected_policy, field))
    # Act / Assert
    with pytest.raises(TypeError, match="immutable tuples"):
        replace(expected_policy, **{field: supplied})


def test_mutable_mapping_pair_is_not_a_closed_policy(expected_policy):
    # Arrange
    supplied = tuple(list(pair) for pair in expected_policy.source_mappings)
    # Act / Assert
    with pytest.raises(TypeError, match="immutable tuples"):
        replace(expected_policy, source_mappings=supplied)
