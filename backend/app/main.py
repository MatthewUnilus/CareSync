from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.db import Base, build_engine, build_session_factory
from app.routers import administrator, auth, clinical, laboratory, meta, ward
from app.seed import seed_demo_users


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(engine)
        if settings.seed_demo_users:
            with session_factory() as session:
                seed_demo_users(session)
                session.commit()
        yield
        engine.dispose()

    app = FastAPI(
        title="CareSync API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    # The browser uses the Vite proxy and never needs CORS. The native shell is
    # a separate origin, so it must be granted credentialed access explicitly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(meta.router)
    app.include_router(clinical.router)
    app.include_router(ward.router)
    app.include_router(laboratory.router)
    app.include_router(administrator.router)
    return app


app = create_app()
