"""Uygulama giriş noktası: `uvicorn app.main:app`."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    application = FastAPI(title="belgeee")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
