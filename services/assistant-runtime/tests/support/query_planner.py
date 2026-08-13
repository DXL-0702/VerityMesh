from collections import deque
from collections.abc import Iterable

from veritymesh_assistant_runtime.query_planning import (
    ProjectQueryPlan,
    QueryPlanningRequest,
)


class ScriptedQueryPlanner:
    """Records task-port calls and replays configured plans or failures."""

    def __init__(self, outcomes: Iterable[ProjectQueryPlan | Exception]) -> None:
        self._outcomes = deque(outcomes)
        self.requests: list[QueryPlanningRequest] = []

    async def plan(self, request: QueryPlanningRequest) -> ProjectQueryPlan:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("scripted query planner has no remaining outcome")

        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
