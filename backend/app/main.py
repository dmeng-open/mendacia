from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import make_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or Settings()
        app.state.settings = resolved
        app.state.engine = make_engine(resolved.database_url)
        yield
        await app.state.engine.dispose()

    app = FastAPI(title="Mendacia", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz(request: Request) -> JSONResponse:
        try:
            async with request.app.state.engine.connect() as conn:
                await conn.execute(text("select 1"))
        except (SQLAlchemyError, OSError) as exc:
            return JSONResponse(status_code=503, content={"status": "error", "db": str(exc)})
        return JSONResponse({"status": "ok", "db": "ok"})

    return app


app = create_app()
