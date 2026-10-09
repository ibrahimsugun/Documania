"""Uygulama giriş noktası: `uvicorn app.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import load_catalog_on_startup
from app.config import Settings, get_settings
from app.db.schema_check import SchemaVersionError, ensure_schema_current, expected_revision
from app.i18n.request import use_request_language
from app.storage import prepare_data_dir
from app.web.auth import LoginRequiredError, login_url, require_api_user, require_panel_user
from app.web.code_watch import CodeWatch
from app.web.routers import (
    access_log,
    auth,
    catalog,
    documents,
    employees,
    groups,
    panel,
    queue,
    training,
    upload_page,
    uploads,
    uploads_list,
    users,
)


def _redirect_to_login(_request: Request, exc: Exception) -> RedirectResponse:
    assert isinstance(exc, LoginRequiredError)
    return RedirectResponse(login_url(exc.next_path), status.HTTP_303_SEE_OTHER)


def _expected_revision_or_none() -> str | None:
    # Göç betikleri yoksa `import app.main` yine çalışır; açılış denetimi o durumda anlaşılır
    # hatayla durur.
    try:
        return expected_revision()
    except SchemaVersionError:
        return None


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        # Ayarlar içe aktarmada değil açılışta okunur: `import app.main` ortam değişkeni
        # olmadan da çalışır, eksik değişken ise sunucu açılırken anlaşılır hata verir (00.2.2).
        resolved = settings or get_settings()
        # 13.5.3: göç koşulmamış (ya da kodun bilmediği ileri) şemayla açılmaz.
        ensure_schema_current(resolved)
        layout = prepare_data_dir(resolved.data_dir)  # 00.4.1: §8.2 ağacı
        # 00.6.2: KnownDocuments/catalog.yaml yoksa tohum; katalog tablosu boşsa dosyadan yüklenir.
        load_catalog_on_startup(resolved.database_url, layout)
        # App yalnız HTTP sunar; kalıcı kuyruğu `python -m app.worker` ayrı süreçte işler.
        yield

    # 10.1.2: girişsiz hiçbir panel yolu açılmaz — otomatik API belgesi sayfaları da kapalı.
    application = FastAPI(
        title="Documania", lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None
    )
    application.add_exception_handler(LoginRequiredError, _redirect_to_login)
    application.add_exception_handler(
        employees.EmployeeDeletedError, employees.employee_deleted_page
    )
    # 13.5.3: açılıştaki kodun parmak izi (eski süreç uyarısı, `/health`'teki `code`) ve bu kodun
    # beklediği şema sürümü. Uygulama nesnesi kurulurken alınır: süreç bellekteki kodu bu andan
    # itibaren değiştirmez.
    application.state.code_watch = CodeWatch()
    application.state.schema_revision = _expected_revision_or_none()
    # Oturumsuz açık olanlar yalnız: giriş/çıkış, `/health` ve stil dosyası (`/static`).
    application.mount("/static", StaticFiles(packages=[("app.web", "static")]), name="static")
    # 10.10.1: sayfa sunan her yolda isteğin dili oturum denetiminden önce çözülür
    # (`app.i18n.request`); JSON API ve `/health` çevrilmez.
    language = Depends(use_request_language)
    panel_page = [language, Depends(require_panel_user)]
    application.include_router(auth.router, dependencies=[language])
    application.include_router(panel.router, dependencies=panel_page)
    application.include_router(upload_page.router, dependencies=panel_page)
    application.include_router(uploads_list.router, dependencies=panel_page)
    # 10.5.13: kalıcı silinen çalışanın bütün adresleri "silindi" sayfasını (410) döner.
    application.include_router(
        employees.router,
        dependencies=[*panel_page, Depends(employees.reject_deleted_employee)],
    )
    application.include_router(documents.router, dependencies=panel_page)
    application.include_router(catalog.router, dependencies=panel_page)
    application.include_router(groups.router, dependencies=panel_page)
    application.include_router(queue.pages_router, dependencies=panel_page)
    application.include_router(access_log.router, dependencies=panel_page)
    application.include_router(training.router, dependencies=panel_page)
    application.include_router(users.router, dependencies=panel_page)
    application.include_router(uploads.router, dependencies=[Depends(require_api_user)])
    application.include_router(queue.router, dependencies=[Depends(require_api_user)])

    @application.get("/health")
    def health() -> dict[str, Any]:
        # Oturumsuz; gizli bilgi yok. `schema`: bu sürecin beklediği (açılışta veritabanında
        # doğrulanan) göç sürümü, `code`: açılıştaki kod parmak izinin kısa hâli (13.5.3).
        return {
            "status": "ok",
            "schema": application.state.schema_revision,
            "code": application.state.code_watch.short,
        }

    return application


app = create_app()
