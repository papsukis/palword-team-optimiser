from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable
import pandas as pd

# Weights for the overall score. Keep them summing to 1.0.
WEIGHTS = {
    "element_match": 0.20,
    "attack_aura": 0.15,
    "defense_aura": 0.10,
    "weakness_amp": 0.15,
    "player_conversion": 0.10,
    "status_synergy": 0.10,
    "mount_utility": 0.05,
    "combat_quality": 0.15,
}

# (buff column in buff_graph, score field name, note shown when present)
BUFF_SPECS = [
    ("Attack Buff", "attack_aura", "{element} attack aura present."),
    ("Defense Buff", "defense_aura", "{element} defense aura present."),
    ("Weakness Amp", "weakness_amp", "{element} weakness amplification present."),
    ("Player Conversion", "player_conversion", "Player damage can be converted to {element}."),
]

# (buff column in buff_graph, candidate flag column, bonus points)
BUFF_BONUS_SPECS = [
    ("Attack Buff", "Has Attack Aura", 10),
    ("Defense Buff", "Has Defense Aura", 7),
    ("Weakness Amp", "Has Weakness Amp", 12),
    ("Player Conversion", "Has Conversion", 10),
]


@dataclass
class TeamScore:
    element_match: float
    attack_aura: float
    defense_aura: float
    weakness_amp: float
    player_conversion: float
    status_synergy: float
    mount_utility: float
    combat_quality: float
    overall: float
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def _has_buff(team_buffs: pd.DataFrame, column: str, element: str) -> float:
    return 100.0 if team_buffs[column].astype(str).str.contains(element, case=False, na=False).any() else 0.0


def score_team(
    team: Iterable[str],
    element: str,
    pals: pd.DataFrame,
    partner_skills: pd.DataFrame,
    buffs: pd.DataFrame,
    statuses: pd.DataFrame,
    mounts: pd.DataFrame,
) -> TeamScore:
    team = [name for name in team if name]
    selected = pals[pals["Pal"].isin(team)].copy()

    notes: list[str] = []
    if not team:
        return TeamScore(0, 0, 0, 0, 0, 0, 0, 0, 0, ["No Pals selected."])

    # Element match
    matching = selected.apply(
        lambda r: element in {str(r.get("Primary Element", "")), str(r.get("Secondary Element", ""))},
        axis=1,
    ).sum()
    element_match = round((matching / len(team)) * 100, 1)

    # Combat quality from existing rating
    rating_col = "Combat Rating (/10)"
    ratings = pd.to_numeric(selected.get(rating_col, pd.Series(dtype=float)), errors="coerce").dropna()
    combat_quality = round((ratings.mean() / 10) * 100, 1) if not ratings.empty else 0.0

    team_buffs = buffs[buffs["Pal"].isin(team)].copy()
    buff_scores = {name: _has_buff(team_buffs, column, element) for column, name, _ in BUFF_SPECS}
    for _, name, note in BUFF_SPECS:
        if buff_scores[name]:
            notes.append(note.format(element=element))

    team_mounts = mounts[mounts["Mount"].isin(team)].copy()
    if team_mounts.empty:
        mount_utility = 0.0
    else:
        combat = pd.to_numeric(team_mounts["Combat Rating"], errors="coerce").fillna(0)
        travel = pd.to_numeric(team_mounts["Travel Rating"], errors="coerce").fillna(0)
        mount_utility = round(((combat.mean() + travel.mean()) / 20) * 100, 1)

    # Status synergy: both applier and consumer in team
    status_hits = []
    for _, row in statuses.iterrows():
        applied_by = _norm(row.get("Applied By"))
        consumed_by = _norm(row.get("Consumed By"))
        has_applier = any(_norm(name) in applied_by for name in team)
        has_consumer = any(_norm(name) in consumed_by for name in team)
        if has_applier and has_consumer:
            status_hits.append(str(row.get("Status")))
    status_synergy = min(100.0, len(status_hits) * 50.0)
    if status_hits:
        notes.append("Complete status combo(s): " + ", ".join(status_hits))
    if not team_mounts.empty:
        notes.append("Combat or traversal mount included.")

    components = {
        "element_match": element_match,
        "status_synergy": status_synergy,
        "mount_utility": mount_utility,
        "combat_quality": combat_quality,
        **buff_scores,
    }
    overall = round(sum(components[key] * weight for key, weight in WEIGHTS.items()), 1)

    return TeamScore(
        element_match=element_match,
        attack_aura=buff_scores["attack_aura"],
        defense_aura=buff_scores["defense_aura"],
        weakness_amp=buff_scores["weakness_amp"],
        player_conversion=buff_scores["player_conversion"],
        status_synergy=status_synergy,
        mount_utility=mount_utility,
        combat_quality=combat_quality,
        overall=overall,
        notes=notes or ["No major synergy detected with the current dataset."],
    )


def rank_candidates(
    element: str,
    pals: pd.DataFrame,
    partner_skills: pd.DataFrame,
    buffs: pd.DataFrame,
    mounts: pd.DataFrame,
) -> pd.DataFrame:
    subset = pals[
        (pals["Primary Element"] == element)
        | (pals["Secondary Element"] == element)
    ].copy()

    for buff_column, flag_column, _ in BUFF_BONUS_SPECS:
        matching_pals = buffs[buffs[buff_column].astype(str).str.contains(element, case=False, na=False)]["Pal"]
        subset[flag_column] = subset["Pal"].isin(matching_pals)
    subset["Is Mount"] = subset["Pal"].isin(mounts["Mount"])

    base = pd.to_numeric(subset["Combat Rating (/10)"], errors="coerce").fillna(0) * 10
    support_bonus = subset["Is Mount"].astype(int) * 5
    for _, flag_column, bonus in BUFF_BONUS_SPECS:
        support_bonus = support_bonus + subset[flag_column].astype(int) * bonus
    subset["Candidate Score"] = (base + support_bonus).clip(upper=100).round(1)

    cols = [
        "Pal",
        "Primary Element",
        "Secondary Element",
        "Role",
        "Combat Rating (/10)",
        "Has Attack Aura",
        "Has Defense Aura",
        "Has Weakness Amp",
        "Has Conversion",
        "Is Mount",
        "Candidate Score",
    ]
    return subset[cols].sort_values(
        ["Candidate Score", "Combat Rating (/10)"],
        ascending=False,
    )


# Roles used when auto-assembling a team, following the game8.co guide:
# https://game8.co/games/Palworld/archives/440398 (2 Ace Attackers of the
# target element + 1 elemental buffer + 2 universal support Pals like
# Orserk/Silvegis, whose buff isn't locked to one element).
ROLE_LABELS = {
    "support": "Universal support",
    "buffer": "Elemental buffer",
    "attacker": "Ace Attacker",
}
ROLE_TARGET_COUNTS = {"buffer": 1, "support": 2, "attacker": 2}
ROLE_PRIORITY = ["buffer", "support", "attacker"]


def _role_of(name: str, universal_pals: set[str], buffer_pals: set[str]) -> str:
    if name in universal_pals:
        return "support"
    if name in buffer_pals:
        return "buffer"
    return "attacker"


def suggest_team(
    element: str,
    locked: Iterable[str],
    pals: pd.DataFrame,
    partner_skills: pd.DataFrame,
    buffs: pd.DataFrame,
    mounts: pd.DataFrame,
) -> list[tuple[str, str]]:
    """Suggest up to 5 Pals for the target element.

    If `locked` already contains Pals, they are kept as-is and only the
    remaining slots are filled around them.
    """
    locked = [name for name in locked if name][:5]
    ranked_names = list(
        rank_candidates(element, pals, partner_skills, buffs, mounts)["Pal"]
    )

    universal_pals = set(
        buffs.loc[
            buffs["Attack Buff"].astype(str).str.strip().eq("All")
            | buffs["Defense Buff"].astype(str).str.strip().eq("All"),
            "Pal",
        ]
    )
    buffer_pals = (
        set(
            buffs.loc[
                buffs["Attack Buff"].astype(str).str.contains(element, case=False, na=False),
                "Pal",
            ]
        )
        - universal_pals
    )

    chosen: set[str] = set(locked)
    counts = {role: 0 for role in ROLE_TARGET_COUNTS}
    for name in locked:
        role = _role_of(name, universal_pals, buffer_pals)
        if role in counts:
            counts[role] += 1

    candidates_by_role = {
        role: [
            n
            for n in ranked_names
            if n not in chosen and _role_of(n, universal_pals, buffer_pals) == role
        ]
        for role in ROLE_TARGET_COUNTS
    }
    fallback = [n for n in ranked_names if n not in chosen]

    team: list[tuple[str, str]] = [(name, "User pick") for name in locked]

    while len(team) < 5:
        pick: tuple[str, str] | None = None
        for role in ROLE_PRIORITY:
            if counts[role] < ROLE_TARGET_COUNTS[role] and candidates_by_role[role]:
                name = candidates_by_role[role].pop(0)
                pick = (name, ROLE_LABELS[role])
                counts[role] += 1
                break
        if pick is None:
            # Every role quota is already filled (or has no eligible Pal left
            # for this element) -- any extra slot is just more firepower.
            remaining = [n for n in fallback if n not in chosen]
            if not remaining:
                break
            pick = (remaining[0], ROLE_LABELS["attacker"])

        chosen.add(pick[0])
        for names in candidates_by_role.values():
            if pick[0] in names:
                names.remove(pick[0])
        team.append(pick)

    return team
