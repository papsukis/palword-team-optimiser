from __future__ import annotations

import argparse
import base64
import datetime
import mimetypes
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://paldb.cc/fr/"
ROOT_DIR = Path(__file__).resolve().parent
CACHE_DIR = ROOT_DIR / ".cache" / "paldb"
IMAGE_CACHE_DIR = ROOT_DIR / ".cache" / "paldb_images"
DATA_DIR = ROOT_DIR / "data"
USER_AGENT = "palworld-team-optimizer-scraper/1.0 (personal project; contact: ali.belemlih@gmail.com)"
DELAY_SECONDS = 0.4
DATA_DATE = datetime.date.today().isoformat()

ELEMENT_MAP = {
    "Fire": "Fire",
    "Water": "Water",
    "Electricity": "Electric",
    "Leaf": "Grass",
    "Dark": "Dark",
    "Dragon": "Dragon",
    "Earth": "Ground",
    "Ice": "Ice",
    "Normal": "Neutral",
}

# The active-skill element badge renders the French display label, not the
# internal ElementType code, so it needs its own map to the English names
# used everywhere else in the dataset (matching app.py's ELEMENTS list).
ELEMENT_FR_MAP = {
    "Feu": "Fire",
    "Eau": "Water",
    "Électricité": "Electric",
    "Electricité": "Electric",
    "Herbe": "Grass",
    "Ténèbres": "Dark",
    "Dragon": "Dragon",
    "Terre": "Ground",
    "Glace": "Ice",
    "Non élém.": "Neutral",
}

# Keyword classifier for partner-skill descriptions -> buff_graph tags.
# "All" marks a party-wide buff that isn't restricted to one element
# (e.g. Orserk's Attack+Defense aura) so suggest_team can find universal
# support Pals without hardcoding names.
ELEMENT_KEYWORDS_FR = {
    "Fire": "Feu", "Water": "Eau", "Electric": "Électricité", "Grass": "Herbe",
    "Dark": "Ténèbres", "Dragon": "Dragon", "Ground": "Terre", "Ice": "Glace",
}
UNIVERSAL_ATTACK_MARKERS = ["l'attaque et la défense des pals", "attaque des pals combattants"]
UNIVERSAL_DEFENSE_MARKERS = ["dégâts reçus", "réduit les dégâts", "protection", "bouclier"]
CONVERSION_MARKERS = ["convertissant ses attaques en", "transfère son pouvoir"]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch(session: requests.Session, slug: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{slug}.html"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    url = BASE_URL + slug
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            html = resp.text
            cache_path.write_text(html, encoding="utf-8")
            time.sleep(DELAY_SECONDS)
            return html
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}") from last_error


def fetch_roster(session: requests.Session) -> list[tuple[int, str, str, str]]:
    html = fetch(session, "Pals")
    soup = BeautifulSoup(html, "lxml")
    roster = []
    seen_slugs = set()
    for link in soup.select("a.itemname[data-pal-id]"):
        slug = link.get("href", "").strip()
        name = link.get_text(strip=True)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        index_span = link.find_previous_sibling("span", class_="text-white-50")
        index = 0
        if index_span:
            m = re.search(r"\d+", index_span.get_text())
            if m:
                index = int(m.group())
        # The icon <img> sits in the same row, inside the preceding
        # flex-shrink-0 <a> wrapping the row's thumbnail.
        image_url = ""
        row_link = link.find_parent("div", class_="flex-grow-1")
        icon_container = row_link.find_previous_sibling("div", class_="flex-shrink-0") if row_link else None
        if icon_container:
            img = icon_container.select_one("img")
            if img and img.get("src"):
                image_url = img["src"]
        roster.append((index, name, slug, image_url))
    return roster


def fetch_image_base64(session: requests.Session, slug: str, image_url: str) -> str:
    """Download a Pal's icon and return it as a data: URI, empty string on failure."""
    if not image_url:
        return ""
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(image_url).suffix or ".webp"
    cache_path = IMAGE_CACHE_DIR / f"{slug}{ext}"

    if not cache_path.exists():
        try:
            resp = session.get(image_url, timeout=20)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
            time.sleep(DELAY_SECONDS)
        except requests.RequestException:
            return ""

    mime_type = mimetypes.guess_type(cache_path.name)[0] or "image/webp"
    encoded = base64.b64encode(cache_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _card_sections(soup: BeautifulSoup) -> dict[str, dict[str, str]]:
    """Generic parser for the 'card' blocks (Stats, Level 80, Others, Movement)."""
    sections: dict[str, dict[str, str]] = {}
    for card in soup.select("div.card"):
        title_el = card.select_one("h5.card-title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        rows: dict[str, str] = {}
        for row in card.select("div.d-flex.justify-content-between"):
            divs = row.find_all("div", recursive=False)
            if len(divs) < 2:
                continue
            key = divs[0].get_text(strip=True)
            value = divs[-1].get_text(strip=True)
            if key:
                rows[key] = value
        sections[title] = rows
    return sections


def _parse_range(text: str) -> tuple[float | None, float | None]:
    if not text:
        return None, None
    parts = re.split(r"[–‒\-]", text.replace("\xa0", " "))
    parts = [p.strip().replace(" ", "") for p in parts if p.strip()]
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None, None
    return None, None


def _partner_skill(soup: BeautifulSoup) -> tuple[str, str]:
    marker = soup.select_one('a[href="Partner_Skill"]')
    if not marker:
        return "", ""
    header_div = marker.find_parent("div").find_parent("div")
    if not header_div:
        return "", ""
    name_div = header_div.find_next_sibling("div")
    name = ""
    if name_div:
        span = name_div.select_one("span.ms-2")
        name = span.get_text(strip=True) if span else name_div.get_text(strip=True)
    desc = ""
    if name_div:
        desc_block = name_div.find_next_sibling("div", class_="d-flex")
        if desc_block:
            desc_el = desc_block.select_one("div.flex-grow-1")
            if desc_el:
                desc = desc_el.get_text(" ", strip=True)
    return name, desc


def _passive_skills(soup: BeautifulSoup) -> list[str]:
    names = []
    for div in soup.select('div[class*="passive-rank"]'):
        text = div.get_text(strip=True)
        if text:
            names.append(text)
    return list(dict.fromkeys(names))


def _is_mountable(soup: BeautifulSoup, slug: str) -> bool:
    return soup.select_one(f'a[href="{slug}_Saddle"]') is not None


def fetch_passive_skill_descriptions(session: requests.Session) -> dict[str, str]:
    """Passive Skill name -> effect description, from the paldb.cc catalog page.

    The page renders several overlapping tab panes (World Tree, standard,
    etc.) all in the same document, so we scan every passive "card" site-wide
    rather than trying to scope to one pane, keeping the first non-empty
    description for each name.
    """
    html = fetch(session, "Passive_Skills")
    soup = BeautifulSoup(html, "lxml")
    descriptions: dict[str, str] = {}
    for card in soup.select("div.border.bg-dark"):
        name_el = card.select_one('div[class*="passive-rank"]')
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if descriptions.get(name):
            continue
        desc_container = card.select_one("div.p-2")
        desc = ""
        if desc_container:
            first_div = desc_container.find("div", recursive=False)
            if first_div:
                desc = first_div.get_text(" ", strip=True)
        desc = re.sub(r"\s+", " ", desc).rstrip(">").strip()
        descriptions[name] = desc
    return descriptions


def _active_skills(soup: BeautifulSoup) -> list[dict]:
    skills = []
    for card in soup.select("div.card.itemPopup.activeSkill"):
        item_head = card.select_one("div.itemHead")
        head = item_head.select_one(".align-self-center") if item_head else None
        if not head:
            continue
        head_text = head.get_text(" ", strip=True)
        level_match = re.search(r"Lv\.\s*(\d+)", head_text)
        level = int(level_match.group(1)) if level_match else None
        name_el = head.select_one("a")
        name = name_el.get_text(strip=True) if name_el else ""
        # A "Skill Fruit" link on the card means this active skill can be
        # taught to any compatible Pal via that fruit, regardless of whether
        # the Pal learns it naturally.
        transferable = item_head.select_one('a[href*="Skill_Fruit"]') is not None

        element = ""
        elem_div = card.select_one("div.me-auto span")
        if elem_div:
            element = elem_div.get_text(strip=True)

        ps_divs = card.select("div.d-flex.pt-1.px-3 > div.ps-3")
        cooldown = ps_divs[0].get_text(strip=True) if len(ps_divs) > 0 else ""
        power = ps_divs[1].get_text(strip=True) if len(ps_divs) > 1 else ""
        cooldown = re.sub(r"[^\d.]", "", cooldown)
        power = re.sub(r"[^\d.]", "", power.split(":")[-1] if ":" in power else power)

        status = ""
        status_buildup = ""
        agg = card.select_one("div.Aggregate")
        if agg:
            spans = agg.select("span")
            if len(spans) >= 2:
                status = spans[1].get_text(strip=True)
            buildup_div = agg.select_one("div.ms-auto")
            if buildup_div:
                status_buildup = buildup_div.get_text(strip=True)

        if name:
            skills.append(
                {
                    "Level": level,
                    "Skill": name,
                    "Element": ELEMENT_FR_MAP.get(element, element),
                    "Cooldown (s)": cooldown,
                    "Power": power,
                    "Status": status,
                    "Status Build-up": status_buildup,
                    "Transferable": transferable,
                }
            )
    return skills


def classify_buffs(description: str) -> dict[str, str]:
    """Heuristic keyword classifier: partner-skill French description -> buff_graph tags."""
    text = description.lower()
    tags = {"Attack Buff": "", "Defense Buff": "", "Weakness Amp": "", "Player Conversion": ""}

    is_universal_attack = any(m in text for m in UNIVERSAL_ATTACK_MARKERS)
    is_universal_defense = any(m in text for m in UNIVERSAL_DEFENSE_MARKERS)

    matched_element = None
    for element, keyword in ELEMENT_KEYWORDS_FR.items():
        if keyword.lower() in text:
            matched_element = element
            break

    if any(m in text for m in CONVERSION_MARKERS) and matched_element:
        tags["Player Conversion"] = matched_element

    if is_universal_attack:
        tags["Attack Buff"] = "All"
    elif matched_element and ("attaque" in text) and ("augmente" in text or "boost" in text or "+" in description):
        tags["Attack Buff"] = matched_element

    if is_universal_defense or is_universal_attack:
        tags["Defense Buff"] = "All"
    elif matched_element and ("défense" in text or "defense" in text):
        tags["Defense Buff"] = matched_element

    if "faiblesse" in text or "vuln" in text:
        if matched_element:
            tags["Weakness Amp"] = matched_element

    return tags


def parse_pal_page(html: str, name: str, slug: str, index: int) -> dict:
    soup = BeautifulSoup(html, "lxml")
    sections = _card_sections(soup)
    stats = sections.get("Stats", {})
    lvl80 = sections.get("Level 80", {})
    others = sections.get("Others", {})

    elem1 = ELEMENT_MAP.get(others.get("ElementType1", ""), "")
    elem2 = ELEMENT_MAP.get(others.get("ElementType2", ""), "")

    hp_min, hp_max = _parse_range(lvl80.get("PV", ""))
    atk_min, atk_max = _parse_range(lvl80.get("Attaque", ""))
    def_min, def_max = _parse_range(lvl80.get("Défense", ""))

    partner_name, partner_desc = _partner_skill(soup)
    passives = _passive_skills(soup)
    active_skills = _active_skills(soup)

    return {
        "Pal": name,
        "Index": index,
        "Primary Element": elem1,
        "Secondary Element": elem2,
        "Rarity": stats.get("Rarity", ""),
        "HP": stats.get("PV", ""),
        "Attack": stats.get("Attaque", ""),
        "Defense": stats.get("Défense", ""),
        "Work Speed": stats.get("Vitesse de travail", ""),
        "Support": stats.get("Support", ""),
        "HP Lvl80 Min": hp_min,
        "HP Lvl80 Max": hp_max,
        "Attack Lvl80 Min": atk_min,
        "Attack Lvl80 Max": atk_max,
        "Defense Lvl80 Min": def_min,
        "Defense Lvl80 Max": def_max,
        "Partner Skill": partner_name,
        "Partner Skill Description": partner_desc,
        "Passive Skills": passives,
        "Active Skills": active_skills,
        "Mountable": _is_mountable(soup, slug),
        "Ride Sprint Speed": sections.get("Movement", {}).get("RideSprintSpeed", ""),
        "Source URL": BASE_URL + slug,
        "Data Date": DATA_DATE,
    }


def scrape_all(limit: int | None = None) -> tuple[list[dict], dict[str, str]]:
    session = _session()
    roster = fetch_roster(session)
    if limit:
        roster = roster[:limit]
    rows = []
    for i, (index, name, slug, image_url) in enumerate(roster, start=1):
        html = fetch(session, slug)
        row = parse_pal_page(html, name, slug, index)
        row["Image Base64"] = fetch_image_base64(session, slug, image_url)
        rows.append(row)
        print(f"[{i}/{len(roster)}] {name} ({slug})")
    passive_descriptions = fetch_passive_skill_descriptions(session)
    return rows, passive_descriptions


def build_datasets(rows: list[dict], passive_descriptions: dict[str, str] | None = None) -> dict[str, pd.DataFrame]:
    passive_descriptions = passive_descriptions or {}
    pals_df = pd.DataFrame(rows)

    def _num(col: str) -> pd.Series:
        return pd.to_numeric(pals_df[col], errors="coerce")

    atk_avg = (_num("Attack Lvl80 Min") + _num("Attack Lvl80 Max")) / 2
    def_avg = (_num("Defense Lvl80 Min") + _num("Defense Lvl80 Max")) / 2
    hp_avg = (_num("HP Lvl80 Min") + _num("HP Lvl80 Max")) / 2

    def _norm01(s: pd.Series) -> pd.Series:
        lo, hi = s.min(), s.max()
        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            return s * 0
        return (s - lo) / (hi - lo)

    atk_n, def_n, hp_n = _norm01(atk_avg), _norm01(def_avg), _norm01(hp_avg)
    combat_rating = (0.45 * atk_n + 0.35 * def_n + 0.20 * hp_n) * 10
    pals_df["Combat Rating (/10)"] = combat_rating.round(1)

    atk_def_ratio = (atk_avg / def_avg.replace(0, pd.NA)).fillna(1)
    role = pd.Series("All-Rounder", index=pals_df.index)
    role[atk_def_ratio > 1.3] = "Attacker"
    role[atk_def_ratio < 0.77] = "Tank"
    pals_df["Role"] = role

    pals_df["Passive Skill"] = pals_df["Passive Skills"].apply(lambda v: ", ".join(v) if v else "")

    pal_cols = [
        "Pal", "Index", "Primary Element", "Secondary Element", "Rarity",
        "HP", "Attack", "Defense", "Work Speed", "Support",
        "HP Lvl80 Min", "HP Lvl80 Max", "Attack Lvl80 Min", "Attack Lvl80 Max",
        "Defense Lvl80 Min", "Defense Lvl80 Max", "Combat Rating (/10)", "Role",
        "Partner Skill", "Passive Skill", "Mountable", "Source URL", "Data Date",
    ]
    pals_out = pals_df[pal_cols].copy()

    partner_rows = []
    buff_rows = []
    for row in rows:
        if not row["Partner Skill"]:
            continue
        tags = classify_buffs(row["Partner Skill Description"])
        statuses = sorted({s["Status"] for s in row["Active Skills"] if s["Status"]})
        partner_rows.append(
            {
                "Pal": row["Pal"],
                "Partner Skill": row["Partner Skill"],
                "Primary Element": row["Primary Element"],
                "Secondary Element": row["Secondary Element"],
                "Description": row["Partner Skill Description"],
                **tags,
                "Source URL": row["Source URL"],
                "Data Date": row["Data Date"],
            }
        )
        buff_rows.append(
            {
                "Pal": row["Pal"],
                "Attack Buff": tags["Attack Buff"],
                "Defense Buff": tags["Defense Buff"],
                "Weakness Amp": tags["Weakness Amp"],
                "Player Conversion": tags["Player Conversion"],
                "Status Applied": ", ".join(statuses),
                "Status Consumed": "",
                "Resistance": "",
                "Healing": "",
                "Mount": "Yes" if row["Mountable"] else "",
                "Comments": "",
            }
        )
    partner_skills_out = pd.DataFrame(partner_rows)
    buff_graph_out = pd.DataFrame(buff_rows)

    mount_rows = []
    ride_speed = pals_df["Ride Sprint Speed"].apply(lambda v: pd.to_numeric(v, errors="coerce"))
    ride_n = _norm01(ride_speed)
    for i, row in pals_df.iterrows():
        if not row["Mountable"]:
            continue
        mount_rows.append(
            {
                "Mount": row["Pal"],
                "Element": row["Primary Element"],
                "Combat Rating": row["Combat Rating (/10)"],
                "Travel Rating": round(float(ride_n.loc[i]) * 10, 1),
                "Source URL": row["Source URL"],
                "Data Date": row["Data Date"],
            }
        )
    mount_engine_out = pd.DataFrame(mount_rows)

    active_catalog: dict[str, dict] = {}
    pal_active_rows = []
    for row in rows:
        for skill in row["Active Skills"]:
            if skill["Skill"] not in active_catalog:
                active_catalog[skill["Skill"]] = {
                    "Skill": skill["Skill"],
                    "Element": skill["Element"],
                    "Cooldown (s)": skill["Cooldown (s)"],
                    "Power": skill["Power"],
                    "Status": skill["Status"],
                    "Status Build-up": skill["Status Build-up"],
                    "Transferable": skill["Transferable"],
                    "Source URL": row["Source URL"],
                    "Data Date": row["Data Date"],
                }
            elif skill["Transferable"]:
                active_catalog[skill["Skill"]]["Transferable"] = True
            pal_active_rows.append({"Pal": row["Pal"], "Level": skill["Level"], "Skill": skill["Skill"]})
    active_skills_out = pd.DataFrame(list(active_catalog.values()))
    pal_active_skills_out = pd.DataFrame(pal_active_rows)

    passive_catalog: dict[str, dict] = {}
    pal_passive_rows = []
    for row in rows:
        for passive in row["Passive Skills"]:
            if passive not in passive_catalog:
                passive_catalog[passive] = {
                    "Passive Skill": passive,
                    "Description": passive_descriptions.get(passive, ""),
                    "Source URL": row["Source URL"],
                    "Data Date": row["Data Date"],
                }
            pal_passive_rows.append({"Pal": row["Pal"], "Passive Skill": passive})
    passive_skills_out = pd.DataFrame(list(passive_catalog.values()))
    pal_passive_skills_out = pd.DataFrame(pal_passive_rows)

    pal_images_out = pd.DataFrame(
        [
            {
                "Pal": row["Pal"],
                "Image Base64": row["Image Base64"],
                "Source URL": row["Source URL"],
                "Data Date": row["Data Date"],
            }
            for row in rows
            if row["Image Base64"]
        ]
    )

    return {
        "pals.csv": pals_out,
        "partner_skills.csv": partner_skills_out,
        "buff_graph.csv": buff_graph_out,
        "mount_engine.csv": mount_engine_out,
        "active_skills.csv": active_skills_out,
        "pal_active_skills.csv": pal_active_skills_out,
        "passive_skills.csv": passive_skills_out,
        "pal_passive_skills.csv": pal_passive_skills_out,
        "pal_images.csv": pal_images_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape paldb.cc into data/*.csv")
    parser.add_argument("--limit", type=int, default=None, help="Only scrape the first N Pals (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Print row counts instead of writing CSVs")
    args = parser.parse_args()

    rows, passive_descriptions = scrape_all(limit=args.limit)
    datasets = build_datasets(rows, passive_descriptions)

    for filename, df in datasets.items():
        if args.dry_run:
            print(f"{filename}: {len(df)} rows")
            continue
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(DATA_DIR / filename, index=False)
        print(f"Wrote {len(df)} rows to data/{filename}")


if __name__ == "__main__":
    main()
