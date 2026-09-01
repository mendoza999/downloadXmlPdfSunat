from fastapi import FastAPI
from app.api.routes import router
from app.core.database import engine, Base
from app.core.logging import setup_logging

logger = setup_logging()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="SUNAT Descargas API", version="1.0")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando servidor FastAPI...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)