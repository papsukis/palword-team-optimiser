from __future__ import annotations

from pathlib import Path
import pandas as pd
from sqlalchemy import Boolean, Column, Float, Integer, MetaData, Table, Text

from db import get_engine

DATA_DIR = Path(__file__).resolve().parent / "data"

# table_name -> {csv filename, column schema}
# Column types are explicit (instead of letting pandas.to_sql infer them) so
# the schema is predictable across re-runs -- notably Text for the base64
# image blobs and free-form descriptions, which pandas would otherwise size
# based on whatever happens to be in the first batch of rows.
TABLES: dict[str, dict] = {
    "pals": {
        "csv": "pals.csv",
        "columns": {
            "Pal": Text, "Index": Integer, "Primary Element": Text, "Secondary Element": Text,
            "Rarity": Float, "HP": Float, "Attack": Float, "Defense": Float,
            "Work Speed": Float, "Support": Float,
            "HP Lvl80 Min": Float, "HP Lvl80 Max": Float,
            "Attack Lvl80 Min": Float, "Attack Lvl80 Max": Float,
            "Defense Lvl80 Min": Float, "Defense Lvl80 Max": Float,
            "Combat Rating (/10)": Float, "Role": Text,
            "Partner Skill": Text, "Passive Skill": Text, "Mountable": Boolean,
            "Source URL": Text, "Data Date": Text,
        },
    },
    "partner_skills": {
        "csv": "partner_skills.csv",
        "columns": {
            "Pal": Text, "Partner Skill": Text, "Primary Element": Text, "Secondary Element": Text,
            "Description": Text, "Attack Buff": Text, "Defense Buff": Text,
            "Weakness Amp": Text, "Player Conversion": Text,
            "Source URL": Text, "Data Date": Text,
        },
    },
    "active_skills": {
        "csv": "active_skills.csv",
        "columns": {
            "Skill": Text, "Element": Text, "Cooldown (s)": Float, "Power": Float,
            "Status": Text, "Status Build-up": Float,
            "Source URL": Text, "Data Date": Text,
        },
    },
    "passive_skills": {
        "csv": "passive_skills.csv",
        "columns": {"Passive Skill": Text, "Source URL": Text, "Data Date": Text},
    },
    "buff_graph": {
        "csv": "buff_graph.csv",
        "columns": {
            "Pal": Text, "Attack Buff": Text, "Defense Buff": Text, "Weakness Amp": Text,
            "Player Conversion": Text, "Status Applied": Text, "Status Consumed": Text,
            "Resistance": Text, "Healing": Text, "Mount": Text, "Comments": Text,
        },
    },
    "status_engine": {
        "csv": "status_engine.csv",
        "columns": {
            "Status": Text, "Applied By": Text, "Consumed By": Text,
            "Primary Element": Text, "Recommended Combo": Text,
        },
    },
    "mount_engine": {
        "csv": "mount_engine.csv",
        "columns": {
            "Mount": Text, "Element": Text, "Combat Rating": Float, "Travel Rating": Float,
            "Source URL": Text, "Data Date": Text,
        },
    },
    "pal_active_skills": {
        "csv": "pal_active_skills.csv",
        "columns": {"Pal": Text, "Level": Integer, "Skill": Text},
    },
    "pal_passive_skills": {
        "csv": "pal_passive_skills.csv",
        "columns": {"Pal": Text, "Passive Skill": Text},
    },
    "pal_images": {
        "csv": "pal_images.csv",
        "columns": {"Pal": Text, "Image Base64": Text, "Source URL": Text, "Data Date": Text},
    },
}


def _drop_empty_unnamed_columns(df: pd.DataFrame) -> pd.DataFrame:
    junk = [c for c in df.columns if str(c).startswith("Unnamed:") and df[c].isna().all()]
    return df.drop(columns=junk)


def main() -> None:
    engine = get_engine()
    metadata = MetaData()

    for table_name, spec in TABLES.items():
        Table(table_name, metadata, *(Column(name, col_type) for name, col_type in spec["columns"].items()))

    # Explicitly drop the old tables and recreate them from the schema above,
    # rather than relying on to_sql(if_exists="replace")'s implicit behavior.
    metadata.drop_all(engine)
    metadata.create_all(engine)

    for table_name, spec in TABLES.items():
        path = DATA_DIR / spec["csv"]
        df = _drop_empty_unnamed_columns(pd.read_csv(path))
        df = df[[c for c in spec["columns"] if c in df.columns]]
        df.to_sql(table_name, engine, if_exists="append", index=False)
        print(f"Loaded {len(df)} rows into '{table_name}' from {spec['csv']}")


if __name__ == "__main__":
    main()
