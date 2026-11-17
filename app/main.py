from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core import config
from app.core.database import Base, engine
from app.core.logging import setup_logging

# Importar los modelos asegura que SQLAlchemy los registre antes del create_all
import app.models.db_models  # noqa: E402,F401

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Base de datos lista: %s", config.DATABASE_URL)
    yield


app = FastAPI(title=config.API_TITLE, version=config.API_VERSION, lifespan=lifespan)

_origins = [o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()]
if not _origins:
    _origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # El navegador no permite credenciales junto con el comodin "*"
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", tags=["salud"])
def raiz():
    return {"servicio": config.API_TITLE, "version": config.API_VERSION, "estado": "ok"}


@app.get("/health", tags=["salud"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import os

    import uvicorn

    logger.info("Iniciando servidor FastAPI...")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=config.UVICORN_RELOAD,
        root_path=config.ROOT_PATH,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
