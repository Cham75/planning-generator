from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class Category(str, Enum):
    OPEN_TIME = "Open Time"
    TEAM_LEAD = "Team Lead"
    SUPERVISEUR = "ENC_Superviseur"
    CONTROLE_QUALITE = "ENC_Controleur qualite"
    EXPERT_METIER = "ENC_Expert Metier"
    NON_ELIGIBLE = "Non éligible"


ELIGIBLE_CATEGORIES = {
    Category.OPEN_TIME,
    Category.TEAM_LEAD,
    Category.SUPERVISEUR,
    Category.CONTROLE_QUALITE,
    Category.EXPERT_METIER,
}


@dataclass(frozen=True)
class Slot:
    start_minute: int
    end_minute: int
    need: int

    @property
    def key(self) -> str:
        return f"{self.start_minute:04d}-{self.end_minute:04d}"

    @property
    def label(self) -> str:
        def fmt(value: int) -> str:
            hour, minute = divmod(value, 60)
            return f"{hour}h" if minute == 0 else f"{hour}h{minute:02d}"

        return f"{fmt(self.start_minute)}–{fmt(self.end_minute)}"


@dataclass
class ActivityInterval:
    source_file: str
    source_sheet: str
    source_row: int
    agent_id: str
    agent_name: str
    work_date: date
    global_start: Optional[int]
    global_end: Optional[int]
    activity: str
    activity_start: Optional[int]
    activity_end: Optional[int]
    category: Category = Category.NON_ELIGIBLE


@dataclass
class AgentProfile:
    agent_id: str
    name: str
    role: str = "À définir"
    excluded: bool = False
    notes: str = ""


@dataclass
class AgentDay:
    agent_id: str
    name: str
    role: str
    work_date: date
    excluded: bool
    global_start: Optional[int]
    global_end: Optional[int]
    intervals: list[ActivityInterval] = field(default_factory=list)
    eligible_slots: dict[str, Category] = field(default_factory=dict)

    @property
    def mandatory(self) -> bool:
        return bool(self.eligible_slots) and not self.excluded


@dataclass
class Assignment:
    work_date: date
    slot_key: str
    agent_id: str
    agent_name: str
    role: str
    category: Category


@dataclass
class Issue:
    severity: str
    issue_type: str
    message: str
    work_date: Optional[date] = None
    agent_id: str = ""
    agent_name: str = ""


@dataclass
class DaySchedule:
    work_date: date
    assignments: list[Assignment]
    uncovered: dict[str, int]
    unmet_mandatory: list[str]
    used_relaxed_mode: bool = False


@dataclass
class ScheduleResult:
    slots: list[Slot]
    days: list[DaySchedule]
    agent_days: list[AgentDay]
    intervals: list[ActivityInterval]
    issues: list[Issue]
    selected_sources: list[str]

    @property
    def assignments(self) -> list[Assignment]:
        return [assignment for day in self.days for assignment in day.assignments]
