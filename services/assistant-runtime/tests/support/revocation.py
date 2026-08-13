from collections import deque
from collections.abc import Iterable

from veritymesh_assistant_runtime.revocation import (
    RevocationCheckRequest,
    RevocationCheckResult,
)


class ScriptedRevocationChecker:
    """Records check requests and replays configured decisions or failures."""

    def __init__(self, outcomes: Iterable[RevocationCheckResult | Exception]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[RevocationCheckRequest] = []

    async def check(self, request: RevocationCheckRequest) -> RevocationCheckResult:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("scripted revocation checker has no remaining outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
