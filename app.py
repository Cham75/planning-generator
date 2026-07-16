from __future__ import annotations

import hashlib
import tempfile
import traceback
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

from planning_tool.config import AppConfig
from planning_tool.exporter import ExcelExporter
from planning_tool.models import AgentProfile
from planning_tool.parser import NiceWorkbookParser
from planning_tool.scheduler import PlanningScheduler
from planning_tool.utils import normalize_name, safe_filename
from web_store import MemoryAgentStore, load_profiles, profiles_to_json


ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "data" / "agents_seed.json"

st.set_page_config(page_title="Planning Assistance", page_icon="📅", layout="wide")


@st.cache_resource
def load_services() -> tuple[AppConfig, NiceWorkbookParser, ExcelExporter]:
    config = AppConfig.load_default()
    return config, NiceWorkbookParser(config), ExcelExporter()


def upload_signature(files, config_file) -> str:
    digest = hashlib.sha256()
    for uploaded in files or []:
        digest.update(uploaded.name.encode("utf-8", errors="ignore"))
        digest.update(uploaded.getvalue())
    if config_file is not None:
        digest.update(config_file.getvalue())
    return digest.hexdigest()


def parse_uploads(uploaded_files, parser: NiceWorkbookParser):
    if not uploaded_files:
        raise ValueError("Ajoutez au moins une extraction NICE.")

    original_names: list[str] = []
    with tempfile.TemporaryDirectory(prefix="planning_assistance_") as temp_dir:
        paths: list[str] = []
        for index, uploaded in enumerate(uploaded_files):
            original_names.append(uploaded.name)
            output = Path(temp_dir) / f"{index:02d}_{Path(uploaded.name).name}"
            output.write_bytes(uploaded.getvalue())
            paths.append(str(output))

        candidates = parser.find_candidates(paths)
        if not candidates:
            raise ValueError("Aucune feuille au format NICE n'a été détectée.")
        selected = parser.choose_latest_per_file(candidates)
        intervals, parser_issues = parser.parse(selected)
        if not intervals:
            raise ValueError("Aucune activité exploitable n'a été trouvée dans les feuilles détectées.")

        name_map = {str(Path(path)): original_names[index] for index, path in enumerate(paths)}
        for interval in intervals:
            interval.source_file = name_map.get(str(Path(interval.source_file)), Path(interval.source_file).name)

        selected_labels = []
        for candidate in selected:
            file_name = name_map.get(str(Path(candidate.file_path)), Path(candidate.file_path).name)
            period = "période inconnue"
            if candidate.start_date and candidate.end_date:
                period = f"{candidate.start_date:%d/%m/%Y} → {candidate.end_date:%d/%m/%Y}"
            selected_labels.append(f"{file_name} · {candidate.sheet_name} · {period}")

    return intervals, parser_issues, original_names, selected_labels


def make_agents_dataframe(intervals, base_profiles: list[AgentProfile], config: AppConfig) -> pd.DataFrame:
    store = MemoryAgentStore(base_profiles)
    scheduler = PlanningScheduler(config, store)
    agent_days, _, _ = scheduler.build_agent_days(intervals)

    unique: dict[str, AgentProfile] = {}
    for day in agent_days:
        profile = store.find(day.agent_id, day.name) or AgentProfile(day.agent_id, day.name)
        profile.excluded = bool(day.excluded)
        unique[day.agent_id or day.name] = profile

    rows = [
        {
            "Identifiant": profile.agent_id,
            "Agent": profile.name,
            "Rôle": profile.role,
            "Exclu": profile.excluded,
        }
        for profile in sorted(unique.values(), key=lambda item: normalize_name(item.name))
    ]
    return pd.DataFrame(rows, columns=["Identifiant", "Agent", "Rôle", "Exclu"])


def dataframe_to_profiles(frame: pd.DataFrame) -> list[AgentProfile]:
    profiles: list[AgentProfile] = []
    for row in frame.to_dict(orient="records"):
        profiles.append(
            AgentProfile(
                agent_id=str(row.get("Identifiant", "")).strip(),
                name=str(row.get("Agent", "")).strip(),
                role=str(row.get("Rôle", "À définir")).strip() or "À définir",
                excluded=bool(row.get("Exclu", False)),
            )
        )
    return profiles


def build_excel(intervals, parser_issues, source_names, profiles, config, exporter):
    store = MemoryAgentStore(profiles)
    scheduler = PlanningScheduler(config, store)
    result, _ = scheduler.schedule(intervals, parser_issues, source_names)
    dates = sorted(day.work_date for day in result.days)
    if not dates:
        raise ValueError("Aucune date n'a été trouvée dans l'extraction.")

    filename = safe_filename(
        f"Planning_assistance_{dates[0]:%Y-%m-%d}_{dates[-1]:%Y-%m-%d}.xlsx"
    )
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        exporter.export(result, str(temp_path))
        content = temp_path.read_bytes()
    finally:
        temp_path.unlink(missing_ok=True)
    return filename, content, result


config, parser, exporter = load_services()

st.title("Planning Assistance")
st.caption("Importez l'extraction NICE, vérifiez les rôles, puis téléchargez le planning Excel.")

with st.expander("Configuration des rôles enregistrée précédemment — facultatif"):
    roles_file = st.file_uploader(
        "Importer un fichier agents.json",
        type=["json"],
        key="roles_file",
        help="Facultatif. Le fichier peut être téléchargé plus bas après avoir corrigé les rôles.",
    )

uploaded_files = st.file_uploader(
    "1. Importer une ou plusieurs extractions NICE",
    type=["xlsx"],
    accept_multiple_files=True,
    key="nice_files",
)

if not uploaded_files:
    st.info("Ajoutez un fichier Excel pour commencer.")
    st.stop()

try:
    signature = upload_signature(uploaded_files, roles_file)
    if st.session_state.get("input_signature") != signature:
        with st.spinner("Lecture de l'extraction NICE…"):
            custom_json = roles_file.getvalue() if roles_file is not None else None
            base_profiles = load_profiles(SEED_PATH, custom_json)
            intervals, parser_issues, source_names, selected_labels = parse_uploads(uploaded_files, parser)
            agents_df = make_agents_dataframe(intervals, base_profiles, config)

        st.session_state.input_signature = signature
        st.session_state.intervals = intervals
        st.session_state.parser_issues = parser_issues
        st.session_state.source_names = source_names
        st.session_state.selected_labels = selected_labels
        st.session_state.agents_df = agents_df
        st.session_state.pop("agents_editor", None)
        st.session_state.pop("output_bytes", None)
        st.session_state.pop("output_name", None)
        st.session_state.pop("result_summary", None)
except Exception as exc:
    st.error(str(exc))
    with st.expander("Détail technique"):
        st.code(traceback.format_exc())
    st.stop()

st.success("Extraction détectée : " + " | ".join(st.session_state.selected_labels))

st.subheader("2. Vérifier les agents")
st.caption(
    "Choisissez le rôle des nouveaux agents. Laura Pillier et Adrien Pouchin restent exclus de l'assistance."
)

edited_df = st.data_editor(
    st.session_state.agents_df,
    key="agents_editor",
    hide_index=True,
    use_container_width=True,
    disabled=["Identifiant", "Agent"],
    column_config={
        "Identifiant": st.column_config.TextColumn("ID", width="small"),
        "Agent": st.column_config.TextColumn("Agent", width="large"),
        "Rôle": st.column_config.SelectboxColumn(
            "Rôle",
            options=config.role_options,
            required=True,
            width="medium",
        ),
        "Exclu": st.column_config.CheckboxColumn("Exclu", width="small"),
    },
)

profiles = dataframe_to_profiles(edited_df)
undefined = [profile.name for profile in profiles if profile.role == "À définir"]
if undefined:
    st.warning("Rôle à définir pour : " + ", ".join(undefined))

config_bytes = profiles_to_json(profiles)
st.download_button(
    "Télécharger la liste des rôles",
    data=config_bytes,
    file_name="agents.json",
    mime="application/json",
    help="Conservez ce fichier et réimportez-le la prochaine fois pour retrouver les rôles modifiés.",
)

st.subheader("3. Générer le planning")
if st.button(
    "Générer le planning Excel",
    type="primary",
    disabled=bool(undefined),
    use_container_width=True,
):
    try:
        with st.spinner("Calcul du planning et création du fichier Excel…"):
            filename, content, result = build_excel(
                st.session_state.intervals,
                st.session_state.parser_issues,
                st.session_state.source_names,
                profiles,
                config,
                exporter,
            )
        uncovered = sum(sum(day.uncovered.values()) for day in result.days)
        unmet = sum(len(day.unmet_mandatory) for day in result.days)
        blocking = sum(issue.severity == "Erreur" for issue in result.issues)
        counts = Counter(item.agent_id for item in result.assignments)
        distribution = "—" if not counts else f"{min(counts.values())} à {max(counts.values())} h"

        st.session_state.output_name = filename
        st.session_state.output_bytes = content
        st.session_state.result_summary = {
            "Heures affectées": len(result.assignments),
            "Manques": uncovered,
            "Heures obligatoires manquantes": unmet,
            "Alertes": blocking,
            "Répartition": distribution,
        }
    except Exception as exc:
        st.error(f"Le planning n'a pas pu être généré : {exc}")
        with st.expander("Détail technique"):
            st.code(traceback.format_exc())

if st.session_state.get("output_bytes"):
    summary = st.session_state.result_summary
    columns = st.columns(4)
    columns[0].metric("Heures affectées", summary["Heures affectées"])
    columns[1].metric("Manques", summary["Manques"])
    columns[2].metric("Obligatoires manquantes", summary["Heures obligatoires manquantes"])
    columns[3].metric("Alertes", summary["Alertes"])
    st.caption("Répartition hebdomadaire : " + summary["Répartition"])
    st.download_button(
        "Télécharger le planning Excel",
        data=st.session_state.output_bytes,
        file_name=st.session_state.output_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
