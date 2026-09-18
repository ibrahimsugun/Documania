"""Uygulama giriş noktası: `uvicorn app.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.catalog import install_seed_catalog
from app.config import Settings, get_settings
from app.storage import prepare_data_dir
from app.web.routers import queue, uploads


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        # Ayarlar içe aktarmada değil açılışta okunur: `import app.main` ortam değişkeni
        # olmadan da çalışır, eksik değişken ise sunucu açılırken anlaşılır hata verir (00.2.2).
        layout = prepare_data_dir((settings or get_settings()).data_dir)  # 00.4.1: §8.2 ağacı
        install_seed_catalog(layout)  # 00.6.2: KnownDocuments/catalog.yaml yoksa tohum
        yield

    application = FastAPI(title="belgeee", lifespan=lifespan)
    application.include_router(uploads.router)
    application.include_router(queue.router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
