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
from engine import rank_candidates, suggest_team

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

    # Skills a Pal can be given even if it doesn't learn them naturally:
    # active skills with a Skill Fruit, and any passive (breeding lets you
    # pass almost any passive onto almost any Pal).
    transferable_actives = sorted(
        data["active_skills"].loc[data["active_skills"]["Transferable"] == True, "Skill"].tolist()
    )
    all_passives = sorted(data["passive_skills"]["Passive Skill"].tolist())

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

                # Own skills first, then everything else transferable via
                # Skill Fruit (actives) / breeding (passives).
                active_options = pal_actives + [s for s in transferable_actives if s not in pal_actives]
                passive_options = pal_passives + [p for p in all_passives if p not in pal_passives]

                active_selected = st.multiselect(
                    "Active skills", active_options, default=pal_actives[:3], key=f"active_skills_{i}_{name}"
                )
                if len(active_selected) > 3:
                    st.caption("Only the first 3 are used.")
                    active_selected = active_selected[:3]

                passive_selected = st.multiselect(
                    "Passive skills", passive_options, default=pal_passives[:4], key=f"passive_skills_{i}_{name}"
                )
                if len(passive_selected) > 4:
                    st.caption("Only the first 4 are used.")
                    passive_selected = passive_selected[:4]

            loadouts.append((name, active_selected, passive_selected))

    active_info = data["active_skills"].set_index("Skill")[["Element", "Cooldown (s)", "Power"]]
    passive_info = data["passive_skills"].set_index("Passive Skill")["Description"]

    active_detail_rows = []
    passive_detail_rows = []
    for name, actives, passives in loadouts:
        if not name:
            continue
        for skill in actives:
            info = active_info.loc[skill] if skill in active_info.index else None
            power = float(info["Power"]) if info is not None and pd.notna(info["Power"]) else 0.0
            cooldown = float(info["Cooldown (s)"]) if info is not None and pd.notna(info["Cooldown (s)"]) else 0.0
            active_detail_rows.append(
                {
                    "Pal": name,
                    "Active Skill": skill,
                    "Element": info["Element"] if info is not None else "",
                    "Cooldown (s)": cooldown or None,
                    "Power": power or None,
                    "Power per Cooldown": round(power / cooldown, 1) if cooldown else None,
                }
            )
        for skill in passives:
            passive_detail_rows.append(
                {
                    "Pal": name,
                    "Passive Skill": skill,
                    "Description": passive_info.get(skill, ""),
                }
            )

    if active_detail_rows or passive_detail_rows:
        st.subheader("Loadout summary")
    if active_detail_rows:
        st.markdown("**Active skills**")
        st.dataframe(pd.DataFrame(active_detail_rows), use_container_width=True, hide_index=True)
    if passive_detail_rows:
        st.markdown("**Passive skills**")
        st.dataframe(pd.DataFrame(passive_detail_rows), use_container_width=True, hide_index=True)

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
