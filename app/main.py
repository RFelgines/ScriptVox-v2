from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.books import router as books_router
from app.api.routes.voices import router as voices_router
from app.config import get_settings
from app.core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail-fast: raises ValueError if any required env var is missing
    init_db()
    yield


app = FastAPI(title="ScriptVox", lifespan=lifespan)
app.include_router(books_router, prefix="/books", tags=["books"])
app.include_router(voices_router, prefix="/voices", tags=["voices"])
