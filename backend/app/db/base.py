from sqlalchemy.orm import DeclarativeBase

from app.db.session import engine


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    # Import models here so they register with Base.metadata before create_all.
    # Example:
    #   from app.db import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
