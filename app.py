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
    load_pal_active_skills,
    load_pal_passive_skills,
    load_pal_images,
)
from engine import score_team, rank_candidates, suggest_team

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
        "pal_active_skills": load_pal_active_skills(),
        "pal_passive_skills": load_pal_passive_skills(),
        "images": load_pal_images(),
    }


data = load_all()
pals = data["pals"]

with st.sidebar:
    st.title("Palworld Team Optimizer")
    element = st.selectbox("Target element", ELEMENTS, index=1)

    if st.button("Suggest a team"):
        locked = [st.session_state.get(f"pal_{i}", "") for i in range(1, 6)]
        locked_names = {name for name in locked if name}
        suggestion = suggest_team(element, locked, pals, data["partner_skills"], data["buffs"], data["mounts"])
        new_picks = iter(name for name, _ in suggestion if name not in locked_names)
        for i in range(1, 6):
            key = f"pal_{i}"
            current = st.session_state.get(key, "")
            if current:
                # Re-affirm the existing value so it survives the st.rerun()
                # below (Streamlit only guarantees persistence for keys
                # explicitly written this run, not ones only set by a past
                # frontend interaction).
                st.session_state[key] = current
            else:
                next_pick = next(new_picks, None)
                if next_pick:
                    st.session_state[key] = next_pick
        st.session_state["suggested_roles"] = dict(suggestion)
        st.rerun()

    if st.button("Refresh data"):
        load_all.clear()
        st.rerun()

st.caption("Build and score five-Pal elemental teams using the Phase 1–5 database.")

tab_builder, tab_candidates, tab_reference = st.tabs(
    ["Team Builder", "Element Candidates", "Reference Data"]
)

with tab_builder:
    options = [""] + sorted(pals["Pal"].dropna().astype(str).unique().tolist())
    roles = st.session_state.get("suggested_roles", {})
    images = data["images"]

    active_lookup = data["pal_active_skills"].merge(
        data["active_skills"][["Skill", "Power"]], on="Skill", how="left"
    )
    active_lookup["Power"] = pd.to_numeric(active_lookup["Power"], errors="coerce").fillna(0)

    cols = st.columns(5)
    team = []
    loadouts = []
    for i, col in enumerate(cols, start=1):
        with col:
            name = st.selectbox(f"Pal {i}", options, key=f"pal_{i}")
            team.append(name)
            if name in roles:
                st.caption(roles[name])

            active_selected: list[str] = []
            passive_selected: list[str] = []
            if name:
                image_row = images[images["Pal"] == name]
                if not image_row.empty and image_row.iloc[0]["Image Base64"]:
                    st.image(image_row.iloc[0]["Image Base64"], width=64)

                pal_actives = (
                    active_lookup[active_lookup["Pal"] == name]
                    .sort_values(["Power", "Level"], ascending=[False, True])["Skill"]
                    .tolist()
                )
                pal_passives = data["pal_passive_skills"].loc[
                    data["pal_passive_skills"]["Pal"] == name, "Passive Skill"
                ].tolist()

                active_selected = st.multiselect(
                    "Active skills", pal_actives, default=pal_actives[:3], key=f"active_skills_{i}_{name}"
                )
                if len(active_selected) > 3:
                    st.caption("Only the first 3 are used.")
                    active_selected = active_selected[:3]

                passive_selected = st.multiselect(
                    "Passive skills", pal_passives, default=pal_passives[:4], key=f"passive_skills_{i}_{name}"
                )
                if len(passive_selected) > 4:
                    st.caption("Only the first 4 are used.")
                    passive_selected = passive_selected[:4]

            loadouts.append((name, active_selected, passive_selected))

    result = score_team(team, element, pals, data["partner_skills"], data["buffs"], data["statuses"], data["mounts"])

    metrics = st.columns(4)
    metrics[0].metric("Overall", f"{result.overall:.1f}%")
    metrics[1].metric("Element match", f"{result.element_match:.1f}%")
    metrics[2].metric("Combat quality", f"{result.combat_quality:.1f}%")
    metrics[3].metric("Status synergy", f"{result.status_synergy:.1f}%")

    for note in result.notes:
        st.write(f"- {note}")

    loadout_rows = [
        {
            "Pal": name,
            "Active Skills": ";".join(actives),
            "Passive Skills": ";".join(passives),
        }
        for name, actives, passives in loadouts
        if name
    ]
    if loadout_rows:
        st.subheader("Loadout summary")
        st.dataframe(pd.DataFrame(loadout_rows), use_container_width=True, hide_index=True)

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
                    "Role", "Combat Rating (/10)", "Partner Skill",
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
        "Pals": pals.merge(data["images"][["Pal", "Image Base64"]], on="Pal", how="left")
        .rename(columns={"Image Base64": "Image"})
        .fillna({"Image": ""}),
        "Partner Skills": data["partner_skills"],
        "Active Skills": data["active_skills"],
        "Passive Skills": data["passive_skills"],
        "Status Engine": data["statuses"],
        "Mount Engine": data["mounts"],
    }
    column_config = {"Image": st.column_config.ImageColumn("Image")} if dataset == "Pals" else None
    st.dataframe(data_map[dataset], use_container_width=True, column_config=column_config)
