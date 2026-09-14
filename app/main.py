"""Uygulama giriş noktası: `uvicorn app.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.storage import prepare_data_dir


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        # Ayarlar içe aktarmada değil açılışta okunur: `import app.main` ortam değişkeni
        # olmadan da çalışır, eksik değişken ise sunucu açılırken anlaşılır hata verir (00.2.2).
        prepare_data_dir((settings or get_settings()).data_dir)  # 00.4.1: §8.2 ağacı
        yield

    application = FastAPI(title="belgeee", lifespan=lifespan)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
