import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.catalog import Catalog, load_cases
from app.config import Settings
from app.db import make_engine, sync_engine
from app.games import GameService, NotAccused
from app.routes import cases, games
from app.routes.games import ProblemError, problem_response
from app.schemas import Handles
from app.session import Forbidden

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or Settings()
        app.state.settings = resolved
        app.state.engine = make_engine(resolved.database_url)
        secret = resolved.session_secret
        app.state.secret = secret
        app.state.games = None
        app.state.catalog = Catalog(load_cases(), sync_engine(resolved.database_url))
        if secret is None:
            log.error("SESSION_SECRET is not set; the game routes answer 503 unavailable")
        else:
            app.state.games = GameService(
                app.state.engine,
                app.state.catalog,
                ids=lambda game_id: Handles(secret, game_id),
            )
        yield
        await app.state.engine.dispose()

    app = FastAPI(title="Mendacia", lifespan=lifespan)
    app.include_router(games.router)
    app.include_router(cases.router)

    @app.exception_handler(ProblemError)
    async def on_problem(request: Request, error: ProblemError) -> JSONResponse:
        return problem_response(error)

    @app.exception_handler(Forbidden)
    async def on_forbidden(request: Request, error: Forbidden) -> JSONResponse:
        return problem_response(ProblemError("denied"))

    @app.exception_handler(NotAccused)
    async def on_not_accused(request: Request, error: NotAccused) -> JSONResponse:
        return problem_response(ProblemError("not_accused"))

    @app.exception_handler(RequestValidationError)
    async def on_invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        return problem_response(ProblemError("bad_request"))

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
