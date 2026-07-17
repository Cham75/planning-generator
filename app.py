from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "app_ui.py"
source = SOURCE_PATH.read_text(encoding="utf-8")

source = source.replace(
    'st.sidebar.caption("Génération et gestion des agents · v5")',
    'st.sidebar.caption("Génération et gestion des agents · v6")',
)

source = source.replace(
    '''    assignment_keys = {
        (item.work_date, item.agent_id, item.slot_key) for item in result.assignments
    }
    assist_counts = Counter(
        (item.work_date, item.agent_id) for item in result.assignments
    )
''',
    '''    assignment_keys = {
        (item.work_date, item.agent_id, item.slot_key) for item in result.assignments
    }
    assist_counts = Counter(
        (item.work_date, item.agent_id) for item in result.assignments
    )
    planned_by_agent_day = defaultdict(list)
    for activity in getattr(result, "planned_activities", []):
        planned_by_agent_day[(activity.work_date, activity.agent_id)].append(activity)
''',
    1,
)

source = source.replace(
    '''            value, _, _ = exporter._planning_slot_state(
                agent, slot.start_minute, slot.end_minute, assigned
            )
            row[slot.label] = value
''',
    '''            value, _, _ = exporter._planning_slot_state(
                agent, slot.start_minute, slot.end_minute, assigned
            )
            if not assigned:
                for activity in planned_by_agent_day[(work_date, agent.agent_id)]:
                    if (
                        activity.start_minute < slot.end_minute
                        and activity.end_minute > slot.start_minute
                    ):
                        value = activity.activity_type
                        break
            row[slot.label] = value
''',
    1,
)

source = source.replace(
    '''        if normalized == "Prise d'appels":
            return "background-color: #fff2cc"
''',
    '''        if normalized == "Prise d'appels":
            return "background-color: #fff2cc"
        if normalized == "Morning Brief":
            return "background-color: #d9eaf7; font-weight: 700"
        if normalized == "Picking QVCA":
            return "background-color: #e4dfec; font-weight: 700"
''',
    1,
)

source = source.replace(
    '''        - Open Time et Team Lead sont en prise d’appels de 18h à 20h et ne sont donc pas affectés à l’assistance.
        - La répartition est équilibrée sur la semaine et les heures consécutives sont évitées autant que possible.
''',
    '''        - Open Time et Team Lead sont en prise d’appels de 18h à 20h et ne sont donc pas affectés à l’assistance.
        - De 19h à 20h, les deux positions sont attribuées en priorité aux superviseurs terminant à 20h, avec rotation équitable sur la semaine.
        - Chaque superviseur reçoit un Morning Brief hebdomadaire de 15 minutes entre 11h30 et 15h30, sans simultanéité.
        - Chaque superviseur reçoit deux heures hebdomadaires de Picking QVCA, en deux créneaux d’une heure pouvant être consécutifs.
        - La répartition est équilibrée sur la semaine et les heures consécutives sont évitées autant que possible.
''',
    1,
)

exec(compile(source, str(SOURCE_PATH), "exec"), globals())
