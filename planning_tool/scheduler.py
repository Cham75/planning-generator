from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from .config import AppConfig
from .flow import EdgeHandle, MinCostFlow
from .models import (
    ActivityInterval,
    AgentDay,
    AgentProfile,
    Assignment,
    Category,
    DaySchedule,
    ELIGIBLE_CATEGORIES,
    Issue,
    ScheduleResult,
)
from .storage import AgentStore
from .utils import normalize_name


CATEGORY_EXTRA_COST = {
    Category.OPEN_TIME: 0,
    Category.TEAM_LEAD: 10_000,
    Category.SUPERVISEUR: 20_000,
    Category.CONTROLE_QUALITE: 20_000,
    Category.EXPERT_METIER: 20_000,
}


class PlanningScheduler:
    def __init__(self, config: AppConfig, agent_store: AgentStore) -> None:
        self.config = config
        self.agent_store = agent_store

    def build_agent_days(self, intervals: list[ActivityInterval]) -> tuple[list[AgentDay], list[AgentProfile], list[Issue]]:
        grouped: dict[tuple[str, date], list[ActivityInterval]] = defaultdict(list)
        for interval in intervals:
            grouped[(interval.agent_id, interval.work_date)].append(interval)

        new_profiles: list[AgentProfile] = []
        issues: list[Issue] = []
        agent_days: list[AgentDay] = []

        for (agent_id, work_date), day_intervals in sorted(grouped.items(), key=lambda item: (item[0][1], item[1][0].agent_name)):
            name = day_intervals[0].agent_name
            profile, created = self.agent_store.get_or_create(agent_id, name)
            if created:
                new_profiles.append(profile)
            excluded = profile.excluded or agent_id in self.config.excluded_agent_ids or normalize_name(name) in self.config.excluded_name_keys
            starts = [item.global_start for item in day_intervals if item.global_start is not None]
            ends = [item.global_end for item in day_intervals if item.global_end is not None]
            agent_day = AgentDay(
                agent_id=agent_id,
                name=name,
                role=profile.role,
                work_date=work_date,
                excluded=excluded,
                global_start=min(starts) if starts else None,
                global_end=max(ends) if ends else None,
                intervals=sorted(day_intervals, key=lambda item: item.activity_start or -1),
            )
            if not excluded:
                for slot in self.config.slots:
                    covering = [
                        interval
                        for interval in day_intervals
                        if interval.category in ELIGIBLE_CATEGORIES
                        and interval.activity_start is not None
                        and interval.activity_end is not None
                        and interval.activity_start <= slot.start_minute
                        and interval.activity_end >= slot.end_minute
                    ]
                    if not covering:
                        continue
                    category = covering[0].category
                    if slot.start_minute >= 18 * 60 and category in self.config.blocked_categories_after_18:
                        continue
                    agent_day.eligible_slots[slot.key] = category
            else:
                issues.append(
                    Issue(
                        severity="Information",
                        issue_type="Agent exclu",
                        message="Agent exclu de toute assistance.",
                        work_date=work_date,
                        agent_id=agent_id,
                        agent_name=name,
                    )
                )
            agent_days.append(agent_day)
        return agent_days, new_profiles, issues

    def schedule(
        self,
        intervals: list[ActivityInterval],
        parser_issues: list[Issue],
        selected_sources: list[str],
    ) -> tuple[ScheduleResult, list[AgentProfile]]:
        agent_days, new_profiles, issues = self.build_agent_days(intervals)
        issues = list(parser_issues) + issues
        weekly_counts: Counter[str] = Counter()
        day_schedules: list[DaySchedule] = []
        by_date: dict[date, list[AgentDay]] = defaultdict(list)
        for agent_day in agent_days:
            by_date[agent_day.work_date].append(agent_day)

        for work_date in sorted(by_date):
            day_schedule = self._schedule_day(work_date, by_date[work_date], weekly_counts)
            day_schedules.append(day_schedule)
            for assignment in day_schedule.assignments:
                weekly_counts[assignment.agent_id] += 1
            if day_schedule.used_relaxed_mode:
                issues.append(
                    Issue(
                        severity="Avertissement",
                        issue_type="Règle obligatoire irréalisable",
                        message=(
                            "Toutes les heures obligatoires ne pouvaient pas être imposées simultanément "
                            "avec les disponibilités et les besoins de la journée. Le moteur a maximisé le nombre "
                            "d'agents servis avant d'attribuer les heures supplémentaires."
                        ),
                        work_date=work_date,
                    )
                )
            for slot_key, missing in day_schedule.uncovered.items():
                if missing:
                    slot = next(slot for slot in self.config.slots if slot.key == slot_key)
                    issues.append(
                        Issue(
                            severity="Erreur",
                            issue_type="Créneau non couvert",
                            message=f"Il manque {missing} personne(s) sur {slot.label}.",
                            work_date=work_date,
                        )
                    )
            for agent_id in day_schedule.unmet_mandatory:
                agent = next((item for item in by_date[work_date] if item.agent_id == agent_id), None)
                issues.append(
                    Issue(
                        severity="Erreur",
                        issue_type="Heure obligatoire non attribuée",
                        message="Aucun créneau n'a pu être attribué malgré l'éligibilité de l'agent.",
                        work_date=work_date,
                        agent_id=agent_id,
                        agent_name=agent.name if agent else "",
                    )
                )

        result = ScheduleResult(
            slots=self.config.slots,
            days=day_schedules,
            agent_days=agent_days,
            intervals=intervals,
            issues=issues,
            selected_sources=selected_sources,
        )
        return result, new_profiles

    def _schedule_day(self, work_date: date, agents: list[AgentDay], weekly_counts: Counter[str]) -> DaySchedule:
        strict = self._solve_day(
            work_date,
            agents,
            weekly_counts,
            mandatory_lower=True,
            allow_uncovered=False,
        )
        if strict is not None:
            assignments = self._reduce_consecutive(strict, agents, weekly_counts)
            return self._make_day_schedule(work_date, assignments, agents, False)

        relaxed = self._solve_day(
            work_date,
            agents,
            weekly_counts,
            mandatory_lower=False,
            allow_uncovered=False,
        )
        if relaxed is None:
            # Keep every coverable hour instead of returning an empty day when one
            # scarce slot makes perfect coverage mathematically impossible.
            relaxed = self._solve_day(
                work_date,
                agents,
                weekly_counts,
                mandatory_lower=False,
                allow_uncovered=True,
            ) or []
        relaxed = self._reduce_consecutive(relaxed, agents, weekly_counts)
        return self._make_day_schedule(work_date, relaxed, agents, True)

    def _solve_day(
        self,
        work_date: date,
        agents: list[AgentDay],
        weekly_counts: Counter[str],
        mandatory_lower: bool,
        allow_uncovered: bool = False,
    ) -> list[Assignment] | None:
        total_need = sum(slot.need for slot in self.config.slots)
        eligible_agents = [agent for agent in agents if agent.eligible_slots and not agent.excluded]
        if mandatory_lower and len(eligible_agents) > total_need:
            return None

        flow = MinCostFlow()
        source, sink = ("source", work_date), ("sink", work_date)
        flow.set_supply(source, total_need)
        flow.set_supply(sink, -total_need)

        assignment_edges: dict[tuple[str, int, str], EdgeHandle] = {}
        for agent in eligible_agents:
            max_units = min(len(agent.eligible_slots), total_need)
            for unit_number in range(1, max_units + 1):
                unit = ("unit", agent.agent_id, unit_number)
                lower = 1 if mandatory_lower and unit_number == 1 else 0
                # In relaxed mode, the first unit is strongly preferred so the solver
                # maximizes the number of distinct agents receiving their daily hour.
                first_unit_bias = 0 if unit_number == 1 else 30_000
                fairness = weekly_counts[agent.agent_id] * 40 + (unit_number - 1) * 25
                flow.add_edge(source, unit, 1, cost=first_unit_bias + fairness, lower=lower)
                for slot_key, category in agent.eligible_slots.items():
                    agent_slot = ("agent_slot", agent.agent_id, slot_key)
                    extra_cost = 0 if unit_number == 1 else CATEGORY_EXTRA_COST.get(category, 25_000)
                    handle = flow.add_edge(unit, agent_slot, 1, cost=extra_cost)
                    assignment_edges[(agent.agent_id, unit_number, slot_key)] = handle
            for slot_key in agent.eligible_slots:
                agent_slot = ("agent_slot", agent.agent_id, slot_key)
                slot_node = ("slot", slot_key)
                flow.add_edge(agent_slot, slot_node, 1, cost=0)

        for slot in self.config.slots:
            slot_node = ("slot", slot.key)
            if allow_uncovered:
                # A very expensive synthetic assignment represents one uncovered
                # position. Real agents are always preferred when available.
                flow.add_edge(source, slot_node, slot.need, cost=1_000_000)
            flow.add_edge(slot_node, sink, slot.need, lower=slot.need)

        feasible, _ = flow.solve()
        if not feasible:
            return None

        by_agent = {agent.agent_id: agent for agent in agents}
        assignments: list[Assignment] = []
        seen: set[tuple[str, str]] = set()
        for (agent_id, unit_number, slot_key), handle in assignment_edges.items():
            if flow.flow_on(handle) <= 0 or (agent_id, slot_key) in seen:
                continue
            agent = by_agent[agent_id]
            category = agent.eligible_slots[slot_key]
            assignments.append(
                Assignment(
                    work_date=work_date,
                    slot_key=slot_key,
                    agent_id=agent_id,
                    agent_name=agent.name,
                    role=agent.role,
                    category=category,
                )
            )
            seen.add((agent_id, slot_key))
        return assignments

    def _make_day_schedule(self, work_date: date, assignments: list[Assignment], agents: list[AgentDay], relaxed: bool) -> DaySchedule:
        assigned_counts = Counter(item.slot_key for item in assignments)
        uncovered = {slot.key: max(0, slot.need - assigned_counts[slot.key]) for slot in self.config.slots}
        assigned_agents = {item.agent_id for item in assignments}
        unmet = [agent.agent_id for agent in agents if agent.mandatory and agent.agent_id not in assigned_agents]
        return DaySchedule(
            work_date=work_date,
            assignments=sorted(assignments, key=lambda item: (item.slot_key, normalize_name(item.agent_name))),
            uncovered=uncovered,
            unmet_mandatory=unmet,
            used_relaxed_mode=relaxed,
        )

    def _reduce_consecutive(
        self,
        assignments: list[Assignment],
        agents: list[AgentDay],
        weekly_counts: Counter[str],
    ) -> list[Assignment]:
        """Best-effort replacement pass; never sacrifices coverage or a mandatory daily hour."""
        by_id = {agent.agent_id: agent for agent in agents}
        slot_order = {slot.key: index for index, slot in enumerate(self.config.slots)}
        current = list(assignments)

        for _ in range(4):
            changed = False
            assignments_by_agent: dict[str, list[Assignment]] = defaultdict(list)
            assigned_pairs = {(item.agent_id, item.slot_key) for item in current}
            for item in current:
                assignments_by_agent[item.agent_id].append(item)

            for agent_id, agent_assignments in sorted(assignments_by_agent.items()):
                ordered = sorted(agent_assignments, key=lambda item: slot_order[item.slot_key])
                if len(ordered) <= 1:
                    continue
                consecutive_targets = [
                    ordered[index + 1]
                    for index in range(len(ordered) - 1)
                    if slot_order[ordered[index + 1].slot_key] == slot_order[ordered[index].slot_key] + 1
                ]
                for target in consecutive_targets:
                    if len(assignments_by_agent[agent_id]) <= 1:
                        break
                    replacement = self._find_replacement(
                        target,
                        current,
                        agents,
                        assigned_pairs,
                        assignments_by_agent,
                        slot_order,
                        weekly_counts,
                    )
                    if replacement:
                        current.remove(target)
                        current.append(replacement)
                        changed = True
                        break
                if changed:
                    break
            if not changed:
                break
        return current

    def _find_replacement(
        self,
        target: Assignment,
        current: list[Assignment],
        agents: list[AgentDay],
        assigned_pairs: set[tuple[str, str]],
        assignments_by_agent: dict[str, list[Assignment]],
        slot_order: dict[str, int],
        weekly_counts: Counter[str],
    ) -> Assignment | None:
        current_priority = CATEGORY_EXTRA_COST.get(target.category, 25_000)
        candidates = []
        for agent in agents:
            if agent.excluded or target.slot_key not in agent.eligible_slots:
                continue
            if (agent.agent_id, target.slot_key) in assigned_pairs:
                continue
            category = agent.eligible_slots[target.slot_key]
            priority = CATEGORY_EXTRA_COST.get(category, 25_000)
            if priority > current_priority:
                continue
            existing_indexes = {slot_order[item.slot_key] for item in assignments_by_agent.get(agent.agent_id, [])}
            index = slot_order[target.slot_key]
            creates_consecutive = index - 1 in existing_indexes or index + 1 in existing_indexes
            if creates_consecutive:
                continue
            total = weekly_counts[agent.agent_id] + len(assignments_by_agent.get(agent.agent_id, []))
            candidates.append((priority, total, normalize_name(agent.name), agent, category))
        if not candidates:
            return None
        _, _, _, agent, category = min(candidates)
        return Assignment(
            work_date=target.work_date,
            slot_key=target.slot_key,
            agent_id=agent.agent_id,
            agent_name=agent.name,
            role=agent.role,
            category=category,
        )
