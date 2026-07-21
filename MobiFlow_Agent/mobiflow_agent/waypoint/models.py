"""语义航点序列数据模型。一条序列 = 一种行为 = 采集器一个标签。"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import (
    DEFAULT_MOBILE_ACTIONS,
    PathConstraint,
    StrictModel,
    VerificationSpec,
)


class WaypointStrength(str, Enum):
    COMMONSENSE = "commonsense"
    STRICT = "strict"


class RendezvousSpec(StrictModel):
    """支柱三(跨设备协同)预留;本轮调度器忽略此字段。"""

    barrier_id: str = Field(min_length=1)
    role: str = Field(min_length=1)


class Waypoint(StrictModel):
    waypoint_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    arrival_spec: VerificationSpec
    strength: WaypointStrength = WaypointStrength.COMMONSENSE
    path_constraint: PathConstraint | None = None
    rendezvous: RendezvousSpec | None = None
    allowed_actions: list[str] = Field(default_factory=lambda: list(DEFAULT_MOBILE_ACTIONS))


class WaypointSequence(StrictModel):
    sequence_id: str = Field(min_length=1)
    behavior_label: str = Field(min_length=1)
    profile_package: str = Field(min_length=1)
    waypoints: list[Waypoint]

    @model_validator(mode="after")
    def validate_waypoints(self) -> "WaypointSequence":
        if not self.waypoints:
            raise ValueError("WaypointSequence requires at least one waypoint.")
        ids = [wp.waypoint_id for wp in self.waypoints]
        if len(ids) != len(set(ids)):
            raise ValueError("WaypointSequence waypoint_id values must be unique.")
        return self
