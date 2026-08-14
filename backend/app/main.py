from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers.generate import router as generate_router
from .routers.vision import router as vision_router
from .routers.config import router as config_router

app = FastAPI(
    title="AIVCS Backend",
    description="Local AI Virtual Character Studio backend (Phase 1: mock providers).",
    version=config.BACKEND_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router)
app.include_router(vision_router)
app.include_router(config_router)


@app.on_event("startup")
async def _startup():
    config.write_runtime_token_file()


@app.get("/")
async def root():
    return {"name": config.BACKEND_NAME, "version": config.BACKEND_VERSION, "docs": "/docs"}
