"""Exact repository lookup; an unregistered prototype grants no owner support."""

from dataclasses import dataclass

from .policy import PackagePolicy


@dataclass(frozen=True)
class PolicyRegistry:
    """An immutable, explicitly supplied reviewed owner table."""

    policies: tuple[PackagePolicy, ...] = ()

    def __post_init__(self):
        if not isinstance(self.policies, tuple) or any(
            not isinstance(policy, PackagePolicy) for policy in self.policies
        ):
            raise TypeError("registered owner policies must be immutable tuples")
        names = [policy.repository for policy in self.policies]
        if len(names) != len(set(names)):
            raise ValueError("duplicate registered release owner")

    def resolve(self, repository):
        if not isinstance(repository, str):
            raise TypeError("repository identity must be a string")
        matches = [
            policy for policy in self.policies if policy.repository == repository
        ]
        if len(matches) != 1:
            raise ValueError("release owner is not registered")
        return matches[0]


# Algorithm fixtures are deliberately not a production registration table.
DEFAULT_REGISTRY = PolicyRegistry()
