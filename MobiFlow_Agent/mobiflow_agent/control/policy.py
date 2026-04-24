from mobiflow_agent.common.contracts import StrictModel


class TaskControlPolicy(StrictModel):
    allow_recovery: bool = True
