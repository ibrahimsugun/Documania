"""Uygulama giriş noktası: `uvicorn app.main:app`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.catalog import load_catalog_on_startup
from app.config import Settings, get_settings
from app.db.schema_check import SchemaVersionError, ensure_schema_current, expected_revision
from app.i18n.request import use_request_language
from app.storage import prepare_data_dir
from app.web.auth import (
    SAFE_METHODS,
    LoginRequiredError,
    api_write_gate,
    login_url,
    panel_write_gate,
    require_api_user,
    require_panel_user,
    require_root,
)
from app.web.code_watch import CodeWatch
from app.web.feedback import READ_ONLY, add_toasts, flash, is_htmx, render, status_feedback
from app.web.routers import (
    access_log,
    ai_settings,
    auth,
    catalog,
    documents,
    employees,
    generated_documents,
    groups,
    output_templates,
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


def _with_feedback(request: Request, response: Response, status_code: int) -> Response:
    """Panelin yazma isteğinin hata yanıtına özet bildirim ekler (10.11.1, PLAN.md §D120): HTMX'te
    `HX-Trigger` başlığı, tam sayfa gönderiminde bir sonraki sayfanın göstereceği çerez. JSON API
    (`/api/...`), okuma istekleri ve oturumsuzluk (401) bildirim almaz."""
    key = status_feedback(status_code)
    if key is None or request.method in SAFE_METHODS or request.url.path.startswith("/api/"):
        return response
    # 10.1.8: yetki reddi (salt okunur Kullanıcı'nın yazma isteği) kendi metniyle.
    if status_code == status.HTTP_403_FORBIDDEN:
        key = READ_ONLY
    if is_htmx(request):
        add_toasts(response, [render(key)])
    else:
        flash(response, key)
    return response


async def _http_error_with_feedback(request: Request, exc: Exception) -> Response:
    """Yanıt FastAPI'nin varsayılanıdır (JSON `detail`); yazma isteğine bildirim eklenir."""
    assert isinstance(exc, HTTPException)
    response = await http_exception_handler(request, exc)
    return _with_feedback(request, response, exc.status_code)


async def _invalid_request_with_feedback(request: Request, exc: Exception) -> Response:
    """Doğrulanamayan form (422) — yanıt FastAPI'nin varsayılanıdır, yazma isteğine bildirim."""
    assert isinstance(exc, RequestValidationError)
    response = await request_validation_exception_handler(request, exc)
    return _with_feedback(request, response, response.status_code)


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
    application.add_exception_handler(HTTPException, _http_error_with_feedback)
    application.add_exception_handler(RequestValidationError, _invalid_request_with_feedback)
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
    # 10.1.8 (PLAN.md §D115 c): yazan her yol — güvenli olmayan her yöntem — İK ya da root ister;
    # Kullanıcı'ya 403. Kapının dışında yalnız giriş/çıkış ve dil seçici (`auth.router`) ile kişinin
    # kendi hesabı (`users.account_router`: parola, Telegram) kalır.
    panel_writes = [*panel_page, Depends(panel_write_gate)]
    api_writes = [Depends(require_api_user), Depends(api_write_gate)]
    application.include_router(auth.router, dependencies=[language])
    application.include_router(panel.router, dependencies=panel_writes)
    application.include_router(upload_page.router, dependencies=panel_writes)
    application.include_router(uploads_list.router, dependencies=panel_writes)
    # 10.5.13: kalıcı silinen çalışanın bütün adresleri "silindi" sayfasını (410) döner.
    application.include_router(
        employees.router,
        dependencies=[*panel_writes, Depends(employees.reject_deleted_employee)],
    )
    # 15.2.1, 15.2.2: profilden çıktıya hazırla ve üretilen belgeler; aynı kapılar.
    application.include_router(
        generated_documents.router,
        dependencies=[*panel_writes, Depends(employees.reject_deleted_employee)],
    )
    application.include_router(documents.router, dependencies=panel_writes)
    application.include_router(catalog.router, dependencies=panel_writes)
    application.include_router(groups.router, dependencies=panel_writes)
    application.include_router(output_templates.router, dependencies=panel_writes)
    application.include_router(queue.pages_router, dependencies=panel_writes)
    application.include_router(access_log.router, dependencies=panel_writes)
    # 10.1.10 (PLAN.md §D124 e): root kapısı yazma kapısından önce — İK ve Kullanıcı'nın `POST`'u
    # da 403 değil, bilinmeyen yolla aynı 404'tür. Yazma kapısı yine yoldadır (rota taraması).
    application.include_router(
        ai_settings.router,
        dependencies=[*panel_page, Depends(require_root), Depends(panel_write_gate)],
    )
    application.include_router(training.router, dependencies=panel_writes)
    application.include_router(users.router, dependencies=panel_writes)
    application.include_router(users.account_router, dependencies=panel_page)
    application.include_router(uploads.router, dependencies=api_writes)
    application.include_router(queue.router, dependencies=api_writes)

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
