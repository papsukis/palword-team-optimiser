from __future__ import annotations

import streamlit as st
import pandas as pd

from data_loader import (
    load_pals,
    load_partner_skills,
    load_active_skills,
    load_passive_skills,
    load_buff_graph,
    load_status_engine,
    load_mount_engine,
)
from engine import score_team, rank_candidates

st.set_page_config(page_title="Palworld Team Optimizer", layout="wide")

ELEMENTS = ["Neutral", "Fire", "Water", "Electric", "Grass", "Ice", "Ground", "Dark", "Dragon"]


@st.cache_data(show_spinner="Loading data from the database...")
def load_all() -> dict[str, pd.DataFrame]:
    return {
        "pals": load_pals(),
        "partner_skills": load_partner_skills(),
        "active_skills": load_active_skills(),
        "passive_skills": load_passive_skills(),
        "buffs": load_buff_graph(),
        "statuses": load_status_engine(),
        "mounts": load_mount_engine(),
    }


with st.sidebar:
    st.title("Palworld Team Optimizer")
    element = st.selectbox("Target element", ELEMENTS, index=1)
    if st.button("Refresh data"):
        load_all.clear()
        st.rerun()

data = load_all()
pals = data["pals"]

st.caption("Build and score five-Pal elemental teams using the Phase 1–5 database.")

tab_builder, tab_candidates, tab_reference = st.tabs(
    ["Team Builder", "Element Candidates", "Reference Data"]
)

with tab_builder:
    options = [""] + sorted(pals["Pal"].dropna().astype(str).unique().tolist())
    cols = st.columns(5)
    team = [
        col.selectbox(f"Pal {i}", options, key=f"pal_{i}")
        for i, col in enumerate(cols, start=1)
    ]

    result = score_team(team, element, pals, data["partner_skills"], data["buffs"], data["statuses"], data["mounts"])

    metrics = st.columns(4)
    metrics[0].metric("Overall", f"{result.overall:.1f}%")
    metrics[1].metric("Element match", f"{result.element_match:.1f}%")
    metrics[2].metric("Combat quality", f"{result.combat_quality:.1f}%")
    metrics[3].metric("Status synergy", f"{result.status_synergy:.1f}%")

    for note in result.notes:
        st.write(f"- {note}")

    with st.expander("Score breakdown"):
        score_df = pd.DataFrame(
            {
                "Category": [
                    "Attack aura",
                    "Defense aura",
                    "Weakness amplifier",
                    "Player conversion",
                    "Mount utility",
                ],
                "Score": [
                    result.attack_aura,
                    result.defense_aura,
                    result.weakness_amp,
                    result.player_conversion,
                    result.mount_utility,
                ],
            }
        )
        st.bar_chart(score_df.set_index("Category"))

        selected = pals[pals["Pal"].isin([x for x in team if x])]
        if not selected.empty:
            show_cols = [
                c for c in [
                    "Pal", "Primary Element", "Secondary Element",
                    "Primary Role", "Combat Rating (/10)", "Partner Skill",
                    "Overall Score", "Notes"
                ] if c in selected.columns
            ]
            st.dataframe(selected[show_cols], use_container_width=True)

with tab_candidates:
    ranked = rank_candidates(element, pals, data["partner_skills"], data["buffs"], data["mounts"])
    st.dataframe(ranked, use_container_width=True, hide_index=True)

with tab_reference:
    dataset = st.selectbox(
        "Dataset",
        ["Pals", "Partner Skills", "Active Skills", "Passive Skills", "Status Engine", "Mount Engine"],
    )
    data_map = {
        "Pals": pals,
        "Partner Skills": data["partner_skills"],
        "Active Skills": data["active_skills"],
        "Passive Skills": data["passive_skills"],
        "Status Engine": data["statuses"],
        "Mount Engine": data["mounts"],
    }
    st.dataframe(data_map[dataset], use_container_width=True)
