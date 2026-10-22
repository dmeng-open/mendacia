from functools import cache

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


@cache
def sync_engine(database_url: str) -> sa.Engine:
    return sa.create_engine(database_url, pool_pre_ping=True)
