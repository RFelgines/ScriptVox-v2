from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.books import router as books_router
from app.api.routes.characters import router as characters_router
from app.api.routes.voices import router as voices_router
from app.config import get_settings
from app.core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail-fast: raises ValueError if any required env var is missing
    init_db()
    yield


app = FastAPI(title="ScriptVox", lifespan=lifespan)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router, prefix="/books", tags=["books"])
app.include_router(characters_router, prefix="/characters", tags=["characters"])
app.include_router(voices_router, prefix="/voices", tags=["voices"])
