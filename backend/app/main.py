from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import deps
from app.api.routes_catalogue import router as catalogue_router
from app.api.routes_recommend import router
from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging


def create_app(load_catalogue: bool = True) -> FastAPI:
    settings = get_settings()

    # @app.on_event("startup") is deprecated (FastAPI emits a DeprecationWarning)
    # in favour of a lifespan context manager; this achieves the same one-shot
    # warm-up without the warning. setup_logging() lives here too rather than
    # in create_app() itself: TestClient(app) only runs this block when used as
    # a context manager, so tests that build several apps in one process (and
    # never enter that block) can't have one app's logging handler bind to a
    # stale stderr/capsys stream and starve a later test's log assertions.
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        setup_logging()
        if load_catalogue:
            # Load catalogue and vectors once, not per request. Also fails fast
            # on a manifest mismatch rather than at first query. Both
            # /api/recommend and /api/catalogue read this same loaded index, so
            # there is nothing else here to warm up or degrade separately.
            deps.get_pipeline()
        yield

    app = FastAPI(title="Personal Shopping Assistant", version="1.0.0",
                  lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",  # preview deployments
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.envelope())

    app.include_router(router)
    app.include_router(catalogue_router)

    return app


app = create_app()
