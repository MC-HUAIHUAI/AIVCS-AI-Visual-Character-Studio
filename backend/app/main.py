from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers.generate import router as generate_router

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


@app.get("/")
async def root():
    return {"name": config.BACKEND_NAME, "version": config.BACKEND_VERSION, "docs": "/docs"}
