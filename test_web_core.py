from __future__ import annotations

import tempfile
from pathlib import Path

from planning_tool.config import AppConfig
from planning_tool.exporter import ExcelExporter
from planning_tool.parser import NiceWorkbookParser
from planning_tool.scheduler import PlanningScheduler
from web_store import MemoryAgentStore, load_profiles


ROOT = Path(__file__).resolve().parent


def run_smoke(input_path: Path) -> tuple[int, int, int]:
    config = AppConfig.load_default()
    parser = NiceWorkbookParser(config)
    candidates = parser.find_candidates([str(input_path)])
    assert candidates, f"Aucune feuille NICE détectée dans {input_path.name}"
    selected = parser.choose_latest_per_file(candidates)
    intervals, issues = parser.parse(selected)
    assert intervals

    profiles = load_profiles(ROOT / "data" / "agents_seed.json")
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


if __name__ == "__main__":
    import sys

    for raw in sys.argv[1:]:
        path = Path(raw)
        print(path.name, run_smoke(path))
