from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

load_dotenv()

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Define it in the environment or in a .env file, "
                "e.g. DATABASE_URL=postgresql://user:password@host:5432/palworld_optimizer"
            )
        _engine = create_engine(database_url)
    return _engine
