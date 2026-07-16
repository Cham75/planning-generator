from __future__ import annotations

import hashlib
import tempfile
import traceback
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from planning_tool.config import AppConfig
from planning_tool.exporter import ExcelExporter, FRENCH_DAYS, ROLE_ORDER
from planning_tool.models import AgentProfile, ScheduleResult
from planning_tool.parser import NiceWorkbookParser
from planning_tool.scheduler import PlanningScheduler
from planning_tool.utils import format_minutes, normalize_name, safe_filename
from web_store import (
    BrowserLocalStorageAgentRepository,
    MemoryAgentStore,
    SessionAgentRepository,
    load_seed_profiles,
    profiles_from_json_bytes,
    profiles_to_json,
)


ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT / "data" / "agents_seed.json"

st.set_page_config(
    page_title="Planning Assistance",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f6f8fb; }
        [data-testid="stSidebar"] { background: #eef3f8; }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.2rem; }
        .main .block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px; }
        .app-hero {
            background: linear-gradient(115deg, #173f65, #245f8f);
            border-radius: 14px;
            padding: 24px 28px;
            color: white;
            margin-bottom: 20px;
            box-shadow: 0 5px 18px rgba(23, 63, 101, 0.15);
        }
        .app-hero h1 { margin: 0; font-size: 2rem; line-height: 1.2; }
        .app-hero p { margin: 7px 0 0 0; color: #dceaf5; font-size: 0.98rem; }
        .section-card {
            background: white;
            border: 1px solid #dce3ea;
            border-radius: 12px;
            padding: 18px 20px 8px 20px;
            margin: 0 0 16px 0;
            box-shadow: 0 2px 8px rgba(31, 78, 120, 0.04);
        }
        .section-title { font-size: 1.08rem; font-weight: 700; color: #173f65; margin-bottom: 4px; }
        .section-subtitle { color: #657382; font-size: 0.9rem; margin-bottom: 10px; }
        .storage-ok, .storage-warning {
            border-radius: 8px; padding: 9px 11px; font-size: 0.86rem; margin: 8px 0 14px 0;
        }
        .storage-ok { background: #e8f5ec; color: #1f6b38; border: 1px solid #b9dfc5; }
        .storage-warning { background: #fff6df; color: #7a5a00; border: 1px solid #ecd58b; }
        div[data-testid="stDataEditor"] { background: white; border-radius: 10px; }
        div[data-testid="stFileUploader"] section { background: #f3f6f9; border-color: #c9d4df; }
        .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
            background: #1f4e78; border-color: #1f4e78;
        }
        .stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
            background: #173f65; border-color: #173f65;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="app-hero">
          <h1>Planning Assistance</h1>
          <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_intro(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="section-title">{title}</div>'
        + (f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""),
        unsafe_allow_html=True,
    )


@st.cache_resource

def load_services() -> tuple[AppConfig, NiceWorkbookParser, ExcelExporter]:
    config = AppConfig.load_default()
    return config, NiceWorkbookParser(config), ExcelExporter()


def get_repository_with_status():
    seed_profiles = load_seed_profiles(SEED_PATH)
    storage_error = ""
    try:
        from browser_storage import StreamlitBrowserStorage

        browser_storage = StreamlitBrowserStorage("planning_assistance_agents_v1")
        if not browser_storage.loaded:
            st.info("Chargement de la liste des agents…")
            st.stop()
        if not browser_storage.available:
            raise RuntimeError(browser_storage.error or "Stockage navigateur indisponible")
        repository = BrowserLocalStorageAgentRepository(
            storage=browser_storage,
            session_cache=st.session_state,
        )
        before_seed = len(repository.list_profiles())
        repository.ensure_seed(seed_profiles)
        if before_seed == 0:
            st.rerun()
    except Exception:
        storage_error = (
            "Le navigateur a bloqué la sauvegarde locale. Les rôles restent disponibles "
            "pendant cette session seulement ; utilisez l’export JSON comme sauvegarde."
        )
        repository = SessionAgentRepository(st.session_state)
        repository.ensure_seed(seed_profiles)
    return repository, storage_error


def payload_signature(payloads: tuple[tuple[str, bytes], ...]) -> str:
    digest = hashlib.sha256()
    for name, content in payloads:
        digest.update(name.encode("utf-8", errors="ignore"))
        digest.update(content)
    return digest.hexdigest()


def _write_payloads(payloads: tuple[tuple[str, bytes], ...], directory: str) -> tuple[list[str], dict[str, int]]:
    paths: list[str] = []
    path_to_index: dict[str, int] = {}
    for index, (name, content) in enumerate(payloads):
        safe_name = Path(name).name or f"extraction_{index + 1}.xlsx"
        path = Path(directory) / f"{index:03d}_{safe_name}"
        path.write_bytes(content)
        paths.append(str(path))
        path_to_index[str(path)] = index
    return paths, path_to_index


@st.cache_data(show_spinner=False)
def analyze_uploaded_workbooks(payloads: tuple[tuple[str, bytes], ...]) -> list[dict]:
    config = AppConfig.load_default()
    parser = NiceWorkbookParser(config)
    with tempfile.TemporaryDirectory(prefix="planning_assistance_scan_") as temp_dir:
        paths, path_to_index = _write_payloads(payloads, temp_dir)
        candidates = parser.find_candidates(paths)
        rows = []
        for candidate in candidates:
            file_index = path_to_index[str(candidate.file_path)]
            start = candidate.start_date
            end = candidate.end_date
            period = "Période inconnue"
            if start and end:
                period = f"{start:%d/%m/%Y} → {end:%d/%m/%Y}"
            key = f"{file_index}::{candidate.sheet_name}"
            rows.append(
                {
                    "key": key,
                    "file_index": file_index,
                    "file_name": payloads[file_index][0],
                    "sheet_name": candidate.sheet_name,
                    "start_date": start,
                    "end_date": end,
                    "period": period,
                    "agent_count": candidate.agent_count,
                    "row_count": candidate.row_count,
                    "label": f"{payloads[file_index][0]} · {candidate.sheet_name} · {period} · {candidate.agent_count} agents",
                }
            )
        return rows


def default_candidate_keys(candidates: list[dict]) -> list[str]:
    grouped: dict[int, list[dict]] = defaultdict(list)
    for candidate in candidates:
        grouped[int(candidate["file_index"])].append(candidate)
    selected = []
    for items in grouped.values():
        latest = max(
            items,
            key=lambda item: (
                item["end_date"] or item["start_date"] or date.min,
                item["start_date"] or date.min,
                item["row_count"],
            ),
        )
        selected.append(latest["key"])
    return selected


@st.cache_data(show_spinner=False)
def parse_selected_workbooks(
    payloads: tuple[tuple[str, bytes], ...], selected_keys: tuple[str, ...]
):
    config = AppConfig.load_default()
    parser = NiceWorkbookParser(config)
    wanted = set(selected_keys)
    with tempfile.TemporaryDirectory(prefix="planning_assistance_parse_") as temp_dir:
        paths, path_to_index = _write_payloads(payloads, temp_dir)
        candidates = parser.find_candidates(paths)
        selected = [
            candidate
            for candidate in candidates
            if f"{path_to_index[str(candidate.file_path)]}::{candidate.sheet_name}" in wanted
        ]
        if not selected:
            raise ValueError("Sélectionnez au moins une feuille NICE.")
        intervals, parser_issues = parser.parse(selected)
        if not intervals:
            raise ValueError("Aucune activité exploitable n'a été trouvée dans les feuilles sélectionnées.")

        selected_labels: list[str] = []
        source_names: list[str] = []
        for candidate in selected:
            file_index = path_to_index[str(candidate.file_path)]
            file_name = payloads[file_index][0]
            source_names.append(file_name)
            period = "Période inconnue"
            if candidate.start_date and candidate.end_date:
                period = f"{candidate.start_date:%d/%m/%Y} → {candidate.end_date:%d/%m/%Y}"
            selected_labels.append(f"{file_name} · {candidate.sheet_name} · {period}")

        for interval in intervals:
            file_index = path_to_index[str(interval.source_file)]
            interval.source_file = payloads[file_index][0]

    return intervals, parser_issues, sorted(set(source_names)), selected_labels


def make_agents_dataframe(
    intervals,
    base_profiles: list[AgentProfile],
    config: AppConfig,
) -> pd.DataFrame:
    known_store = MemoryAgentStore(base_profiles)
    working_store = MemoryAgentStore(base_profiles)
    scheduler = PlanningScheduler(config, working_store)
    agent_days, _, _ = scheduler.build_agent_days(intervals)

    days_by_agent: Counter[str] = Counter(day.agent_id or day.name for day in agent_days)
    unique: dict[str, AgentProfile] = {}
    status: dict[str, str] = {}
    for day in agent_days:
        key = day.agent_id or day.name
        profile = working_store.find(day.agent_id, day.name) or AgentProfile(day.agent_id, day.name)
        profile.excluded = bool(day.excluded)
        unique[key] = profile
        status[key] = "Enregistré" if known_store.find(day.agent_id, day.name) else "Nouveau"

    rows = []
    for key, profile in sorted(unique.items(), key=lambda item: normalize_name(item[1].name)):
        rows.append(
            {
                "Identifiant": profile.agent_id,
                "Agent": profile.name,
                "Rôle": profile.role,
                "Exclu": profile.excluded,
                "Notes": profile.notes,
                "Jours": days_by_agent[key],
                "Statut": status[key],
            }
        )
    return pd.DataFrame(
        rows,
        columns=["Identifiant", "Agent", "Rôle", "Exclu", "Notes", "Jours", "Statut"],
    )


def profiles_dataframe(profiles: list[AgentProfile]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Identifiant": item.agent_id,
                "Agent": item.name,
                "Rôle": item.role,
                "Exclu": item.excluded,
                "Notes": item.notes,
            }
            for item in sorted(profiles, key=lambda profile: normalize_name(profile.name))
        ],
        columns=["Identifiant", "Agent", "Rôle", "Exclu", "Notes"],
    )


def dataframe_to_profiles(frame: pd.DataFrame) -> list[AgentProfile]:
    profiles: list[AgentProfile] = []
    for row in frame.to_dict(orient="records"):
        profiles.append(
            AgentProfile(
                agent_id=str(row.get("Identifiant", "")).strip(),
                name=str(row.get("Agent", "")).strip(),
                role=str(row.get("Rôle", "À définir")).strip() or "À définir",
                excluded=bool(row.get("Exclu", False)),
                notes=str(row.get("Notes", "")).strip(),
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


def preview_dataframe(result: ScheduleResult, work_date: date, exporter: ExcelExporter) -> pd.DataFrame:
    assignment_keys = {
        (item.work_date, item.agent_id, item.slot_key) for item in result.assignments
    }
    assist_counts = Counter(
        (item.work_date, item.agent_id) for item in result.assignments
    )
    agents = [
        item
        for item in result.agent_days
        if item.work_date == work_date and exporter._show_agent_on_day(item)
    ]
    agents.sort(key=lambda item: (ROLE_ORDER.get(item.role, 99), normalize_name(item.name)))

    rows = []
    for agent in agents:
        row = {
            "Rôle": agent.role,
            "Agent": agent.name,
            "Créneau": exporter._working_window(agent),
            "Assistance (h)": "Exclu" if agent.excluded else assist_counts[(work_date, agent.agent_id)],
        }
        for slot in result.slots:
            assigned = (work_date, agent.agent_id, slot.key) in assignment_keys
            value, _, _ = exporter._planning_slot_state(
                agent, slot.start_minute, slot.end_minute, assigned
            )
            row[slot.label] = value
        rows.append(row)
    return pd.DataFrame(rows)


def style_preview(frame: pd.DataFrame):
    def cell_style(value):
        normalized = str(value)
        if normalized == "Assistance":
            return "background-color: #bdd7ee; font-weight: 700"
        if normalized == "Pause déjeuner":
            return "background-color: #c6e0b4"
        if normalized == "Prise d'appels":
            return "background-color: #fff2cc"
        if normalized in {"Congé", "Absence"}:
            return "background-color: #f4b183"
        if normalized in {"Formation", "Réunion", "École / WH"}:
            return "background-color: #f8cbad"
        if normalized == "Repos":
            return "background-color: #d9d9d9"
        return ""

    slot_columns = [column for column in frame.columns if "–" in str(column)]
    return frame.style.map(cell_style, subset=slot_columns).set_properties(
        **{"text-align": "center"}, subset=slot_columns
    )


def repository_banner(repository, storage_error: str) -> None:
    if storage_error:
        st.markdown(f'<div class="storage-warning">{storage_error}</div>', unsafe_allow_html=True)
    elif repository.persistent:
        st.markdown(
            '<div class="storage-ok"><strong>Agents mémorisés dans ce navigateur.</strong> '
            'Les rôles, exclusions et notes sont retrouvés automatiquement, sans base de données. '
            'Les fichiers Excel importés ne sont pas enregistrés.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="storage-warning">Sauvegarde limitée à la session actuelle. '
            'Exportez un fichier JSON depuis « Agents et rôles » pour conserver une copie.</div>',
            unsafe_allow_html=True,
        )


def render_generator(config, exporter, repository, storage_error) -> None:
    hero("Import NICE → vérification des rôles → planning quotidien partagé → Excel")
    repository_banner(repository, storage_error)

    section_intro(
        "1. Extraction(s) en entrée",
        "Ajoutez un ou plusieurs fichiers Excel. L’application détecte les différentes variantes NICE et les feuilles disponibles.",
    )
    uploaded_files = st.file_uploader(
        "Fichiers Excel NICE",
        type=["xlsx"],
        accept_multiple_files=True,
        key="nice_files_v2",
        label_visibility="collapsed",
    )
    if not uploaded_files:
        st.info("Ajoutez une extraction Excel pour commencer.")
        return

    payloads = tuple((item.name, item.getvalue()) for item in uploaded_files)
    upload_sig = payload_signature(payloads)
    try:
        with st.spinner("Détection des feuilles NICE…"):
            candidates = analyze_uploaded_workbooks(payloads)
    except Exception as exc:
        st.error(f"Lecture impossible : {exc}")
        with st.expander("Détail technique"):
            st.code(traceback.format_exc())
        return

    if not candidates:
        st.error("Aucune feuille au format NICE n’a été détectée dans les fichiers importés.")
        return

    label_by_key = {item["key"]: item["label"] for item in candidates}
    default_keys = default_candidate_keys(candidates)
    selected_keys = st.multiselect(
        "Feuilles à utiliser",
        options=list(label_by_key),
        default=default_keys,
        format_func=lambda key: label_by_key[key],
        key=f"sheet_selection_{upload_sig[:12]}",
        help="La feuille la plus récente de chaque fichier est présélectionnée. Vous pouvez choisir une autre semaine.",
    )

    detected_frame = pd.DataFrame(
        [
            {
                "Fichier": item["file_name"],
                "Feuille": item["sheet_name"],
                "Période": item["period"],
                "Agents": item["agent_count"],
                "Lignes": item["row_count"],
                "Sélectionnée": item["key"] in selected_keys,
            }
            for item in candidates
        ]
    )
    with st.expander("Voir les feuilles détectées", expanded=len(candidates) > len(uploaded_files)):
        st.dataframe(detected_frame, hide_index=True, width="stretch")

    if not selected_keys:
        st.warning("Sélectionnez au moins une feuille.")
        return

    try:
        with st.spinner("Lecture et normalisation des horaires…"):
            intervals, parser_issues, source_names, selected_labels = parse_selected_workbooks(
                payloads, tuple(sorted(selected_keys))
            )
    except Exception as exc:
        st.error(str(exc))
        with st.expander("Détail technique"):
            st.code(traceback.format_exc())
        return

    period_dates = sorted({item.work_date for item in intervals})
    detected_agents = {item.agent_id for item in intervals}
    metrics = st.columns(4)
    metrics[0].metric("Fichiers", len(source_names))
    metrics[1].metric("Feuilles", len(selected_keys))
    metrics[2].metric("Agents", len(detected_agents))
    metrics[3].metric("Jours", len(period_dates))
    st.caption("Sélection : " + " | ".join(selected_labels))

    section_intro(
        "2. Agents et rôles",
        "Les rôles déjà enregistrés sont repris automatiquement. Un nouvel agent apparaît avec le statut Nouveau et doit recevoir un rôle via la liste déroulante.",
    )
    try:
        stored_profiles = repository.list_profiles()
    except Exception:
        st.error("Impossible de charger la liste des agents enregistrés.")
        return

    agents_df = make_agents_dataframe(intervals, stored_profiles, config)
    new_count = int((agents_df["Statut"] == "Nouveau").sum()) if not agents_df.empty else 0
    if new_count:
        st.warning(f"{new_count} nouvel agent détecté. Choisissez son rôle avant de générer le planning.")

    roles_revision = int(st.session_state.get("roles_revision", 0))
    editor_key = f"import_agents_{upload_sig[:10]}_{hash(tuple(sorted(selected_keys)))}_{roles_revision}"
    edited_df = st.data_editor(
        agents_df,
        key=editor_key,
        hide_index=True,
        width="stretch",
        height=min(620, 90 + max(1, len(agents_df)) * 35),
        disabled=["Identifiant", "Agent", "Jours", "Statut"],
        column_config={
            "Identifiant": st.column_config.TextColumn("ID", width="small"),
            "Agent": st.column_config.TextColumn("Agent", width="large"),
            "Rôle": st.column_config.SelectboxColumn(
                "Rôle", options=config.role_options, required=True, width="medium"
            ),
            "Exclu": st.column_config.CheckboxColumn("Exclu", width="small"),
            "Notes": st.column_config.TextColumn("Notes", width="large"),
            "Jours": st.column_config.NumberColumn("Jours", width="small"),
            "Statut": st.column_config.TextColumn("Statut", width="small"),
        },
    )
    profiles = dataframe_to_profiles(edited_df)
    undefined = [item.name for item in profiles if item.role == "À définir"]

    save_col, generate_col = st.columns([1, 2])
    if save_col.button("Enregistrer les rôles", width="stretch"):
        try:
            repository.upsert_many(profiles)
            st.session_state.roles_revision = roles_revision + 1
            st.success("Rôles et exclusions enregistrés.")
            st.rerun()
        except Exception as exc:
            st.error(f"Enregistrement impossible : {exc}")

    if generate_col.button(
        "Générer le planning Excel",
        type="primary",
        width="stretch",
        disabled=bool(undefined),
    ):
        try:
            with st.spinner("Calcul du planning et création de l’Excel…"):
                repository.upsert_many(profiles)
                filename, content, result = build_excel(
                    intervals,
                    parser_issues,
                    source_names,
                    profiles,
                    config,
                    exporter,
                )
            uncovered = sum(sum(day.uncovered.values()) for day in result.days)
            unmet = sum(len(day.unmet_mandatory) for day in result.days)
            blocking = sum(issue.severity == "Erreur" for issue in result.issues)
            counts = Counter(item.agent_id for item in result.assignments)
            distribution = "—" if not counts else f"{min(counts.values())} à {max(counts.values())} h"
            st.session_state.generated_output = {
                "name": filename,
                "bytes": content,
                "result": result,
                "summary": {
                    "Heures affectées": len(result.assignments),
                    "Manques": uncovered,
                    "Obligatoires manquantes": unmet,
                    "Alertes": blocking,
                    "Répartition": distribution,
                },
            }
            st.rerun()
        except Exception as exc:
            st.error(f"Le planning n’a pas pu être généré : {exc}")
            with st.expander("Détail technique"):
                st.code(traceback.format_exc())

    if undefined:
        st.caption("Génération bloquée tant que ces rôles ne sont pas définis : " + ", ".join(undefined))

    output = st.session_state.get("generated_output")
    if output:
        section_intro("3. Résultat", "Contrôlez rapidement la couverture puis téléchargez le planning.")
        summary = output["summary"]
        columns = st.columns(4)
        columns[0].metric("Heures affectées", summary["Heures affectées"])
        columns[1].metric("Manques", summary["Manques"])
        columns[2].metric("Obligatoires manquantes", summary["Obligatoires manquantes"])
        columns[3].metric("Alertes", summary["Alertes"])
        st.caption("Répartition hebdomadaire : " + summary["Répartition"])

        result: ScheduleResult = output["result"]
        preview_dates = sorted(day.work_date for day in result.days)
        if preview_dates:
            selected_date = st.selectbox(
                "Aperçu du planning par jour",
                options=preview_dates,
                format_func=lambda value: f"{FRENCH_DAYS[value.weekday()]} {value:%d/%m/%Y}",
            )
            preview = preview_dataframe(result, selected_date, exporter)
            st.dataframe(
                style_preview(preview),
                hide_index=True,
                width="stretch",
                height=min(720, 90 + max(1, len(preview)) * 35),
            )

        st.download_button(
            "Télécharger le planning Excel",
            data=output["bytes"],
            file_name=output["name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )


def render_agents(config, repository, storage_error) -> None:
    hero("Consultez et modifiez la liste permanente des agents")
    repository_banner(repository, storage_error)
    try:
        profiles = repository.list_profiles()
    except Exception as exc:
        st.error(f"Impossible de charger les agents : {exc}")
        return

    section_intro(
        "Liste des agents",
        "Recherchez un agent, modifiez son rôle avec la liste déroulante ou excluez-le de l’assistance.",
    )
    filter_cols = st.columns([2, 1, 1])
    search = filter_cols[0].text_input("Rechercher", placeholder="Nom, identifiant, rôle…")
    role_filter = filter_cols[1].selectbox("Rôle", ["Tous"] + config.role_options)
    state_filter = filter_cols[2].selectbox("Statut", ["Tous", "Actifs", "Exclus", "À définir"])

    filtered = []
    normalized_search = normalize_name(search)
    for profile in profiles:
        haystack = normalize_name(
            f"{profile.agent_id} {profile.name} {profile.role} {profile.notes}"
        )
        if normalized_search and normalized_search not in haystack:
            continue
        if role_filter != "Tous" and profile.role != role_filter:
            continue
        if state_filter == "Actifs" and profile.excluded:
            continue
        if state_filter == "Exclus" and not profile.excluded:
            continue
        if state_filter == "À définir" and profile.role != "À définir":
            continue
        filtered.append(profile)

    total_cols = st.columns(4)
    total_cols[0].metric("Agents", len(profiles))
    total_cols[1].metric("Affichés", len(filtered))
    total_cols[2].metric("Exclus", sum(item.excluded for item in profiles))
    total_cols[3].metric("À définir", sum(item.role == "À définir" for item in profiles))

    revision = int(st.session_state.get("agents_page_revision", 0))
    editor = st.data_editor(
        profiles_dataframe(filtered),
        key=f"agents_directory_{revision}_{role_filter}_{state_filter}_{hash(search)}",
        hide_index=True,
        width="stretch",
        height=min(720, 90 + max(1, len(filtered)) * 35),
        disabled=["Identifiant", "Agent"],
        column_config={
            "Identifiant": st.column_config.TextColumn("ID", width="small"),
            "Agent": st.column_config.TextColumn("Agent", width="large"),
            "Rôle": st.column_config.SelectboxColumn(
                "Rôle", options=config.role_options, required=True, width="medium"
            ),
            "Exclu": st.column_config.CheckboxColumn("Exclu", width="small"),
            "Notes": st.column_config.TextColumn("Notes", width="large"),
        },
    )

    action_cols = st.columns([1, 1, 2])
    if action_cols[0].button("Enregistrer les modifications", type="primary", width="stretch"):
        try:
            repository.upsert_many(dataframe_to_profiles(editor))
            st.session_state.agents_page_revision = revision + 1
            st.success("Modifications enregistrées.")
            st.rerun()
        except Exception as exc:
            st.error(f"Enregistrement impossible : {exc}")

    action_cols[1].download_button(
        "Exporter une sauvegarde JSON",
        data=profiles_to_json(profiles),
        file_name="agents.json",
        mime="application/json",
        width="stretch",
        help="Utile pour transférer les rôles vers un autre ordinateur ou restaurer le navigateur.",
    )

    with st.expander("Importer, transférer ou réinitialiser les agents"):
        st.caption(
            "La mémorisation est automatique sur cet ordinateur. Le fichier JSON sert seulement "
            "de sauvegarde ou pour transférer les rôles vers un autre navigateur."
        )
        backup_file = st.file_uploader(
            "Importer une sauvegarde agents.json",
            type=["json"],
            key="agents_backup_import",
        )
        import_col, reset_col = st.columns(2)
        if import_col.button(
            "Restaurer la sauvegarde",
            disabled=backup_file is None,
            width="stretch",
        ):
            try:
                imported_profiles = profiles_from_json_bytes(backup_file.getvalue())
                if not imported_profiles:
                    raise ValueError("La sauvegarde ne contient aucun agent.")
                repository.replace_all(imported_profiles)
                st.session_state.agents_page_revision = revision + 1
                st.success(f"{len(imported_profiles)} agents restaurés.")
                st.rerun()
            except Exception as exc:
                st.error(f"Restauration impossible : {exc}")

        confirm_reset = st.checkbox(
            "Je confirme vouloir remettre la liste initiale",
            key="confirm_agents_reset",
        )
        if reset_col.button(
            "Réinitialiser la liste",
            disabled=not confirm_reset,
            width="stretch",
        ):
            repository.reset_to_seed(load_seed_profiles(SEED_PATH))
            st.session_state.agents_page_revision = revision + 1
            st.success("Liste initiale restaurée.")
            st.rerun()

    with st.expander("Ajouter manuellement un agent"):
        with st.form("add_agent_form", clear_on_submit=True):
            form_cols = st.columns([1, 2, 1])
            agent_id = form_cols[0].text_input("Identifiant")
            name = form_cols[1].text_input("Nom, prénom")
            role = form_cols[2].selectbox("Rôle", config.role_options)
            excluded = st.checkbox("Exclure de toute assistance")
            notes = st.text_input("Notes")
            submitted = st.form_submit_button("Ajouter l’agent")
            if submitted:
                if not name.strip() and not agent_id.strip():
                    st.error("Saisissez au moins un nom ou un identifiant.")
                else:
                    repository.upsert_many(
                        [
                            AgentProfile(
                                agent_id=agent_id.strip(),
                                name=name.strip(),
                                role=role,
                                excluded=excluded,
                                notes=notes.strip(),
                            )
                        ]
                    )
                    st.session_state.agents_page_revision = revision + 1
                    st.success("Agent ajouté.")
                    st.rerun()


def render_rules(config, repository, storage_error) -> None:
    hero("Règles actives et formats d’entrée pris en charge")
    repository_banner(repository, storage_error)

    section_intro("Couverture demandée")
    st.dataframe(
        pd.DataFrame(
            [{"Créneau": slot.label, "Personnes requises": slot.need} for slot in config.slots]
        ),
        hide_index=True,
        width="stretch",
    )

    section_intro("Règles d’affectation")
    st.markdown(
        """
        - Une heure d’assistance obligatoire par agent éligible et par jour, lorsque la couverture le permet.
        - Les heures supplémentaires sont attribuées en priorité aux Open Time, puis aux Team Lead, puis aux autres catégories.
        - Open Time et Team Lead sont en prise d’appels de 18h à 20h et ne sont donc pas affectés à l’assistance.
        - La répartition est équilibrée sur la semaine et les heures consécutives sont évitées autant que possible.
        - Laura Pillier et Adrien Pouchin sont exclus par défaut. Cette exclusion reste visible et modifiable dans la liste des agents.
        """
    )

    section_intro("Formats NICE reconnus")
    st.markdown(
        """
        - titre avec apostrophe droite ou typographique : `Horaires d'agent` / `Horaires d’agent` ;
        - feuille renommée si la structure `Agent`, `Date` et `Activité planifiée` est présente ;
        - colonne de fin placée à différents endroits ou fin d’activité absente ;
        - plusieurs feuilles dans un même classeur, avec sélection de la semaine par liste déroulante ;
        - semaines de cinq ou six jours, pauses à la demi-heure, congés, formations, réunions et jours libres.
        """
    )


inject_css()
config, parser, exporter = load_services()
repository, storage_error = get_repository_with_status()

st.sidebar.markdown("## Planning Assistance")
st.sidebar.caption("Génération et gestion des agents · v4")
page = st.sidebar.radio(
    "Navigation",
    ["Générer un planning", "Agents et rôles", "Règles et formats"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.caption(f"Stockage : {repository.mode}")
if repository.persistent:
    st.sidebar.success("Agents mémorisés sur ce navigateur")
else:
    st.sidebar.warning("Sauvegarde limitée à cette session")

if page == "Générer un planning":
    render_generator(config, exporter, repository, storage_error)
elif page == "Agents et rôles":
    render_agents(config, repository, storage_error)
else:
    render_rules(config, repository, storage_error)
