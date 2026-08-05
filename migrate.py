from __future__ import annotations

from pathlib import Path
import pandas as pd

from db import get_engine

DATA_DIR = Path(__file__).resolve().parent / "data"

TABLES = {
    "pals.csv": "pals",
    "partner_skills.csv": "partner_skills",
    "active_skills.csv": "active_skills",
    "passive_skills.csv": "passive_skills",
    "buff_graph.csv": "buff_graph",
    "status_engine.csv": "status_engine",
    "mount_engine.csv": "mount_engine",
}


def _drop_empty_unnamed_columns(df: pd.DataFrame) -> pd.DataFrame:
    junk = [c for c in df.columns if str(c).startswith("Unnamed:") and df[c].isna().all()]
    return df.drop(columns=junk)


def main() -> None:
    engine = get_engine()
    for csv_name, table_name in TABLES.items():
        path = DATA_DIR / csv_name
        df = _drop_empty_unnamed_columns(pd.read_csv(path))
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        print(f"Loaded {len(df)} rows into '{table_name}' from {csv_name}")


if __name__ == "__main__":
    main()
