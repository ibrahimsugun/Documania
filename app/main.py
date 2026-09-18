"""Uygulama giriş noktası: `uvicorn app.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import install_seed_catalog
from app.config import Settings, get_settings
from app.storage import prepare_data_dir
from app.web.auth import LoginRequiredError, login_url, require_api_user, require_panel_user
from app.web.routers import auth, documents, employees, panel, queue, upload_page, uploads


def _redirect_to_login(_request: Request, exc: Exception) -> RedirectResponse:
    assert isinstance(exc, LoginRequiredError)
    return RedirectResponse(login_url(exc.next_path), status.HTTP_303_SEE_OTHER)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        # Ayarlar içe aktarmada değil açılışta okunur: `import app.main` ortam değişkeni
        # olmadan da çalışır, eksik değişken ise sunucu açılırken anlaşılır hata verir (00.2.2).
        layout = prepare_data_dir((settings or get_settings()).data_dir)  # 00.4.1: §8.2 ağacı
        install_seed_catalog(layout)  # 00.6.2: KnownDocuments/catalog.yaml yoksa tohum
        yield

    # 10.1.2: girişsiz hiçbir panel yolu açılmaz — otomatik API belgesi sayfaları da kapalı.
    application = FastAPI(
        title="belgeee", lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None
    )
    application.add_exception_handler(LoginRequiredError, _redirect_to_login)
    # Oturumsuz açık olanlar yalnız: giriş/çıkış, `/health` ve stil dosyası (`/static`).
    application.mount("/static", StaticFiles(packages=[("app.web", "static")]), name="static")
    application.include_router(auth.router)
    application.include_router(panel.router, dependencies=[Depends(require_panel_user)])
    application.include_router(upload_page.router, dependencies=[Depends(require_panel_user)])
    application.include_router(employees.router, dependencies=[Depends(require_panel_user)])
    application.include_router(documents.router, dependencies=[Depends(require_panel_user)])
    application.include_router(queue.pages_router, dependencies=[Depends(require_panel_user)])
    application.include_router(uploads.router, dependencies=[Depends(require_api_user)])
    application.include_router(queue.router, dependencies=[Depends(require_api_user)])

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
