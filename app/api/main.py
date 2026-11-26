"""
FastAPI application factory.

    uvicorn api:app                       (api.py; builds the container from the environment)
    create_app(build(settings, ...))      (tests: inject a container with fakes)
"""
import warnings
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import admin, chat, leads, system
from app.container import Container, build


def create_app(container: Optional[Container] = None) -> FastAPI:
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    container = container or build()
    container.settings.knowledge_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="🤖 Document Intelligence & Conversational RAG API",
        description="Enterprise RAG Backend with Admin Ingestion & Website Widget Chat endpoints",
        version="1.1.0",
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
    )
    for module in (admin, chat, leads, system):
        app.include_router(module.router)
    return app
