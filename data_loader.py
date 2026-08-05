from __future__ import annotations

import pandas as pd

from db import get_engine


def _read_table(name: str) -> pd.DataFrame:
    return pd.read_sql_table(name, get_engine()).fillna("")


def load_pals() -> pd.DataFrame:
    return _read_table("pals")


def load_partner_skills() -> pd.DataFrame:
    return _read_table("partner_skills")


def load_active_skills() -> pd.DataFrame:
    return _read_table("active_skills")


def load_passive_skills() -> pd.DataFrame:
    return _read_table("passive_skills")


def load_buff_graph() -> pd.DataFrame:
    return _read_table("buff_graph")


def load_status_engine() -> pd.DataFrame:
    return _read_table("status_engine")


def load_mount_engine() -> pd.DataFrame:
    return _read_table("mount_engine")
