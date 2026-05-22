import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.config import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising database tables…")
    await init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="LLM Chatbot API",
    description="Multi-provider LLM chatbot with inference logging",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "backend"}


@app.get("/api/providers")
async def list_providers():
    from app.sdk.providers import PROVIDER_MAP, DEFAULT_MODELS
    from app.config import settings
    providers = []
    for name in PROVIDER_MAP:
        key_set = bool(getattr(settings, f"{name}_api_key", None))
        providers.append({
            "name": name,
            "default_model": DEFAULT_MODELS[name],
            "configured": key_set,
        })
    return providers
