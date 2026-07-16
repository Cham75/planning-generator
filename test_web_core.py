from __future__ import annotations

import tempfile
from pathlib import Path

from planning_tool.config import AppConfig
from planning_tool.exporter import ExcelExporter
from planning_tool.models import AgentProfile
from planning_tool.parser import NiceWorkbookParser
from planning_tool.scheduler import PlanningScheduler
from web_store import (
    BrowserLocalStorageAgentRepository,
    MemoryAgentStore,
    load_seed_profiles,
    profiles_from_json_bytes,
    profiles_to_json,
)

ROOT = Path(__file__).resolve().parent


class FakeBrowserStorage:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def getItem(self, itemKey: str):
        return self.values.get(itemKey)

    def setItem(self, itemKey: str, itemValue, key: str = "set"):
        self.values[itemKey] = itemValue

    def eraseItem(self, itemKey: str, key: str = "eraseItem", default=None):
        self.values.pop(itemKey, None)


def run_smoke(input_path: Path) -> tuple[int, int, int]:
    config = AppConfig.load_default()
    parser = NiceWorkbookParser(config)
    candidates = parser.find_candidates([str(input_path)])
    assert candidates, f"Aucune feuille NICE détectée dans {input_path.name}"
    selected = parser.choose_latest_per_file(candidates)
    intervals, issues = parser.parse(selected)
    assert intervals

    profiles = load_seed_profiles(ROOT / "data" / "agents_seed.json")
    store = MemoryAgentStore(profiles)
    scheduler = PlanningScheduler(config, store)
    result, _ = scheduler.schedule(intervals, issues, [input_path.name])
    assert result.days

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
        output = Path(handle.name)
    try:
        ExcelExporter().export(result, str(output))
        assert output.exists() and output.stat().st_size > 0
    finally:
        output.unlink(missing_ok=True)
    uncovered = sum(sum(day.uncovered.values()) for day in result.days)
    return len(intervals), len(result.assignments), uncovered


def test_browser_repository_persists_across_sessions() -> None:
    storage = FakeBrowserStorage()
    first_session: dict[str, object] = {}
    seed = load_seed_profiles(ROOT / "data" / "agents_seed.json")[:3]

    repository = BrowserLocalStorageAgentRepository(storage, first_session)
    repository.ensure_seed(seed)
    loaded = repository.list_profiles()
    assert len(loaded) == 3

    loaded[0].role = "Team Lead"
    loaded[0].excluded = True
    repository.upsert_many([loaded[0]])

    # Simulate a full browser refresh: Streamlit session state is empty, while
    # browser localStorage remains available.
    second_session: dict[str, object] = {}
    reopened = BrowserLocalStorageAgentRepository(storage, second_session)
    reloaded = reopened.list_profiles()
    match = next(item for item in reloaded if item.agent_id == loaded[0].agent_id)
    assert match.role == "Team Lead"
    assert match.excluded is True


def test_json_backup_round_trip() -> None:
    profiles = [
        AgentProfile(
            agent_id="123",
            name="Agent Test",
            role="Open Time",
            excluded=True,
            notes="Test",
        )
    ]
    restored = profiles_from_json_bytes(profiles_to_json(profiles))
    assert len(restored) == 1
    assert restored[0].agent_id == "123"
    assert restored[0].role == "Open Time"
    assert restored[0].excluded is True


if __name__ == "__main__":
    import sys

    for raw in sys.argv[1:]:
        path = Path(raw)
        print(path.name, run_smoke(path))
