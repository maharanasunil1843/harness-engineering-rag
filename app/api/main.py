"""FastAPI application entry point."""
import logging

from fastapi import FastAPI

from app.api.middleware import setup_middleware
from app.api.routes import install_validation_handler, router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Harness Engineering RAG",
        description="Agentic RAG over the harness engineering corpus",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    setup_middleware(app)
    install_validation_handler(app)
    app.include_router(router)
    return app


app = create_app()
