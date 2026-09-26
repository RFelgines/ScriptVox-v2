from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes.books import router as books_router
from app.api.routes.characters import router as characters_router
from app.api.routes.merge_suggestions import router as merge_suggestions_router
from app.api.routes.models import router as models_router
from app.api.routes.queue import router as queue_router
from app.api.routes.settings import router as settings_router
from app.api.routes.voices import router as voices_router
from app.config import get_settings
from app.core.db import init_db

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail-fast: raises ValueError if any required env var is missing
    init_db()
    yield


app = FastAPI(title="ScriptVox", lifespan=lifespan)

_settings = get_settings()


@app.middleware("http")
async def block_cross_site_writes(request: Request, call_next):
    """Anti-CSRF pour une API locale sans authentification.

    Un navigateur envoie TOUJOURS l'en-tête Origin sur une requête d'écriture
    cross-origin (formulaire multipart ou fetch « simple », que CORS n'empêche pas
    d'exécuter côté serveur). On refuse donc toute écriture dont l'Origin n'est pas dans
    FRONTEND_ORIGINS (y compris « null »), ou que le navigateur déclare cross-site.
    Les clients hors navigateur (curl, scripts, tests) n'envoient pas d'Origin : acceptés.
    """
    if request.method not in _SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in _settings.frontend_origins:
            return JSONResponse(
                {"detail": f"Cross-origin write refused (Origin {origin!r})."}, status_code=403
            )
        if origin is None and request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site write refused."}, status_code=403)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
# Ajouté en dernier = exécuté en premier : un Host inattendu est rejeté avant tout le reste.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_settings.allowed_hosts)

app.include_router(books_router, prefix="/books", tags=["books"])
app.include_router(characters_router, prefix="/characters", tags=["characters"])
app.include_router(merge_suggestions_router, prefix="/merge-suggestions", tags=["merge-suggestions"])
app.include_router(voices_router, prefix="/voices", tags=["voices"])
app.include_router(settings_router, prefix="/settings", tags=["settings"])
app.include_router(queue_router, prefix="/chapters", tags=["queue"])
app.include_router(models_router, prefix="/models", tags=["models"])
