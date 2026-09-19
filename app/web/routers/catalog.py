"""Katalog yönetim ekranı (PRD 11.1.1, 11.1.2, 11.1.3): Belge Türleri.

- `GET /document-types` bütün türleri (pasifler dahil) listeler; her satırdan düzenlenir,
  pasifleştirilir ya da yeniden etkinleştirilir. `GET /document-types/new` + `POST
  /document-types` tür oluşturur; `GET /document-types/{slug}` (form) + `POST
  /document-types/{slug}` düzenler (`slug` değişmez); `POST /document-types/{slug}/deactivate`
  ve `.../activate` pasifleştirir/etkinleştirir. **Silme yok** (K16).
- Form katalog sözleşmesinden geçer (`app.catalog.form`, 11.1.2): Direkt türde dönüşüm listesi
  boş, `front_back` türde sayfa aralığı 2, analiz edilmeyen türde zorunlu alan yok. Reddedilen
  form 422 ile, girilen değerler ve alan başına mesajla yeniden çizilir; hiçbir şey yazılmaz.
- `acceptance_criteria` (11.1.3) formda madde madde düzenlenir: HTMX'li `POST
  /document-types/criteria/add` ve `.../remove` yalnız madde listesi parçasını yeniler
  (kaydetmez); JavaScript kapalıyken formun sonundaki boş madde alanı ve boşaltılan maddenin
  kaydedilmemesi aynı işi görür. Kayıt her analizde veritabanından baştan okunur
  (`export_catalog`): değişiklik **bir sonraki analizde** geçerli olur — süren analiz ve donmuş
  plan (K9) etkilenmez.
- Bu ekran belge içeriğine dokunmaz (K17); kaynak `known_document_types`'tır, `catalog.yaml`
  yazılmaz.

**Örnek belgeler (11.2.1).** Türün düzenleme sayfasında (`GET /document-types/{slug}`) o türün
örnekleri listelenir ve `POST /document-types/{slug}/examples` ile (çok dosyalı `files`) yenisi
yüklenir; örnek `GET /document-types/{slug}/examples/{ad}` ile açılır. Örnekler
`data/KnownDocuments/examples/<slug>/` altında yalnız dosya olarak durur (`app.storage.examples`):
çalışan verisinden ayrıdır — yükleme, belge, olay kaydı açılmaz, `Inbox/` ve `Employees/`'a girmez —
bu yüzden çalışan/belge aramasında görünmez ve gerçek bir yüklemeyi "tekrar" saymaz. Yükleme
hep-ya-hiçtir: bir dosya reddedilirse (tür PDF/JPEG/PNG dışı, bozuk, boş, boyut sınırını aşan)
hiçbiri yazılmaz ve hata dosya başına bildirilir; aynı içerik ikinci kez yazılmaz. Silme ve
düzenleme yolu yok.

**Tür açıklaması (11.3.1).** Düzenleme sayfasındaki formun "Örneklerden açıklama üret" düğmesi formu
`POST /document-types/{slug}/description`'a gönderir: türün örnek sayfaları (en çok
`MAX_DESCRIPTION_PAGES`) yapay zekâya verilir, yapılandırılmış açıklama (düzen, başlıklar, dil ve
alfabe, alanların yeri, MRZ, ön/arka yüz farkı) üretilir ve metni formun "Analizci için açıklama"
(`prompt_description`) alanına yazılarak form yeniden çizilir; yapılandırılmış hâli ve kullanılan
sayfalar formun üstünde gösterilir. **Kaydedilmez:** İK metni düzenleyip "Kaydet" ile türü
kaydeder (yukarıdaki düzenleme yolu, 11.1.1). Formdaki kaydedilmemiş değerler korunur; açıklama
formdaki tür bilgileriyle (ad, ülke, yüzler, zorunlu alanlar) istenir, bu yüzden form önce
doğrulanır (geçersizse 422, istek gitmez). Örnek yoksa 422, sağlayıcı kurulamıyorsa 503, sağlayıcı
yanıt vermez ya da yanıt şemaya uymazsa 502; hiçbirinde bir şey yazılmaz.

**Aday türler (11.5).** Analizcinin önerdiği katalog dışı türler (04.6.1) `GET
/document-types/candidate-types`'ta listelenir (11.5.1): bekleyen adaylar adı, görülme sayısı, örnek
sayfaları (analiz kopyası, `/uploads/{id}/pages/{page_id}/image`) ve bekleyen Unknown öğe sayısıyla;
onaylanmış ama ilişkili Unknown öğesi hâlâ bekleyen adaylar ayrıca. Yol parçasındaki tire hiçbir
slug'la çakışmaz (slug `[a-z][a-z0-9_]*`). `GET /document-types/candidate-types/{id}` adayın
detayıdır: örnek sayfalar, ilişkili bekleyen Unknown öğeleri (ilk kaynak sayfası adayın örnek
sayfalarından biri olan, partisinin güncel planındaki çözülmemiş öğe — `app.web.routers.queue`'nun
durum tanımı) ve karar:

- **Onay (11.5.2, K16).** Tür formu adayla önceden dolu açılır (`suggested_form`); İK yapıyı
  (dosya türleri, yüzler, Direkt Belge, zorunlu alanlar…) tamamlar. `POST .../approve/confirm` formu
  11.1.2 doğrulamasından geçirir ve §20.6'nın birinci metnini (`<Tür adı>` = formdaki ad) eklenecek
  kaydın özetiyle verir → `POST .../approve/prepare` ikinci metni ve kayda bağlı tek kullanımlık
  belirteci (10.8.1; hedef aday + kaydın SHA-256 özeti) verir → `POST .../approve` belirteci
  tüketir; `USER_CONFIRMED`, türün kataloğa eklenmesi ve `TYPE_APPROVED` tek işlemdedir. Her adım
  adayı ve kaydı yeniden denetler: karara bağlanmış aday 409, geçersiz form 422, katalogda olan slug
  409.
- **Ret (11.5.4).** `POST .../reject` adayı reddeder (`TYPE_REJECTED`, kullanıcı adıyla); K16'nın
  onaylı işlemleri arasında olmadığı için tek adımdır (pasifleştirme gibi). Reddedilen aday listeye
  geri düşmez.
- **Toplu yeniden analiz (11.5.3).** Onaylanmış adayın ilişkili Unknown öğelerinin partileri
  yeniden analiz edilir (06.6.2, K18: her partide yeni plan sürümü, eski çıktılar "eski sürüm").
  Yeniden analiz iki aşamalı onay ister (10.3.2): `POST .../reanalyze/prepare` ikinci metni ve
  partilere + güncel planlarına bağlı belirteci verir, `POST .../reanalyze` hepsini tek işlemde
  yapar — biri düşerse hiçbiri kalmaz. Metinler yeniden analizinkilerin (D23) çoğuludur.

Bu adımlar yalnız katalog ve aday kaydını değiştirir; belge içeriği değişmez (K11, K17).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, replace
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.ai.provider import AnalysisProvider, ProviderConfigError, ProviderError, create_provider
from app.ai.type_description import TypeDescriptionError
from app.catalog import (
    DETAIL_SAMPLE_LIMIT,
    CandidateDecidedError,
    CandidateNotFoundError,
    CatalogEntry,
    Conversion,
    FileType,
    OutputFormat,
    Sides,
    TypeExistsError,
    TypeForm,
    TypeFormError,
    TypeNotFoundError,
    approve_candidate_type,
    approved_type_slug,
    build_entry,
    count_pending_candidate_types,
    create_type,
    export_catalog,
    list_candidate_types,
    list_types,
    load_candidate_type,
    load_record,
    record_problems,
    reject_candidate_type,
    sample_page_refs,
    set_type_active,
    suggested_form,
    summarize_candidates,
    update_type,
)
from app.catalog.describe import (
    MAX_DESCRIPTION_PAGES,
    SCRIPT_LABELS,
    GeneratedDescription,
    NoExamplePagesError,
    TypeNotAnalyzedError,
    describe_type,
)
from app.config import Settings, get_settings
from app.db.models import (
    CandidateDocumentType,
    CandidateTypeStatus,
    KnownDocumentType,
    Plan,
    QueueItem,
    QueueKind,
    Upload,
    UploadFile,
    UploadStatus,
)
from app.db.session import get_session
from app.pipeline.orchestrate import (
    PLAN_EXECUTION_ERRORS,
    PlanExecutor,
    current_plan,
    reanalyze_upload,
)
from app.storage import DataLayout
from app.storage.examples import (
    ExampleRejectedError,
    StoredExample,
    check_example,
    example_path,
    list_examples,
    store_example,
)
from app.web.auth import PanelUser, require_panel_user
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    ConfirmationRefusedError,
    Operation,
    confirm_operation,
    first_text,
    issue_confirmation,
    second_text,
)
from app.web.routers.documents import _reference
from app.web.routers.queue import QueueState, _payload_refs, _state_filter
from app.web.routers.upload_page import (
    BUSY_MESSAGE,
    FINAL_STATUSES,
    ReanalysisProvider,
    ReanalysisProviderError,
    _page_ranges,
)
from app.web.routers.uploads import get_layout, get_plan_executor
from app.web.templating import MENU_BY_KEY, render_page

router = APIRouter(tags=["catalog"])

CurrentUser = Annotated[PanelUser, Depends(require_panel_user)]
DbSession = Annotated[Session, Depends(get_session)]
Layout = Annotated[DataLayout, Depends(get_layout)]
AppSettings = Annotated[Settings, Depends(get_settings)]

LIST_PATH = "/document-types"
TYPE_NOT_FOUND = "Belge türü bulunamadı"
SLUG_TAKEN = "Bu slug'la bir tür zaten var; slug benzersiz olmalı ve sonradan değişmez"

FILE_TYPE_LABELS = {
    FileType.PDF: "PDF",
    FileType.JPEG: "JPEG",
    FileType.PNG: "PNG",
    FileType.DOC: "Word (doc)",
    FileType.DOCX: "Word (docx)",
    FileType.XLS: "Excel (xls)",
    FileType.XLSX: "Excel (xlsx)",
}
SIDES_LABELS = {Sides.SINGLE: "Tek yüz", Sides.FRONT_BACK: "Ön ve arka yüz"}
CONVERSION_LABELS = {
    Conversion.MERGE: "Sayfaları birleştir",
    Conversion.WRAP_IMAGE: "Görüntüyü PDF'e sar",
    Conversion.EXTRACT_IMAGE: "Gömülü görüntüyü çıkar",
    Conversion.RENDER_IMAGE: "Sayfayı görüntüye çevir",
}
OUTPUT_FORMAT_LABELS = {
    OutputFormat.KEEP: "Kaynağın biçimini koru",
    OutputFormat.PDF: "PDF",
    OutputFormat.JPEG: "JPEG",
}
NOTICES = {
    "created": "Tür oluşturuldu.",
    "updated": "Tür güncellendi. Değişiklik bir sonraki analizden itibaren geçerlidir.",
    "deactivated": "Tür pasifleştirildi: yeni belgelere atanmaz.",
    "activated": "Tür yeniden etkinleştirildi.",
}

# --- 11.2: örnek belgeler ------------------------------------------------------------------------

EXAMPLE_NOT_FOUND = "Örnek belge bulunamadı"
NO_EXAMPLE_FILE = "Dosya seçilmedi."

# --- 11.3: tür açıklaması -----------------------------------------------------------------------

DESCRIPTION_INVALID_FORM = "Açıklama üretilmedi: önce alanların altındaki uyarıları düzeltin."
DESCRIPTION_NOT_ANALYZED = (
    "Açıklama üretilmedi: analiz edilmeyen türün açıklaması analizde kullanılmaz."
)
DESCRIPTION_NO_EXAMPLES = (
    "Açıklama üretilmedi: bu türün açılabilen örneği yok. Önce örnek belge yükleyin."
)
DESCRIPTION_PROVIDER_UNAVAILABLE = (
    "Açıklama üretilmedi: yapay zekâ sağlayıcısı kurulamadı. {detail}"
)
DESCRIPTION_PROVIDER_FAILED = (
    "Açıklama üretilmedi: yapay zekâ sağlayıcısı yanıt vermedi ({detail}). Biraz sonra yeniden "
    "deneyin."
)
DESCRIPTION_REJECTED = (
    "Açıklama üretilmedi: yapay zekânın yanıtı tür açıklaması şemasına uymadı. Yeniden deneyin."
)

# --- 11.5: aday türler ---------------------------------------------------------------------------

CANDIDATES_PATH = f"{LIST_PATH}/candidate-types"
CANDIDATE_NOT_FOUND = "Aday tür bulunamadı."
CANDIDATE_STATUS_LABELS = {
    CandidateTypeStatus.PENDING.value: "Onay bekliyor",
    CandidateTypeStatus.APPROVED.value: "Onaylandı",
    CandidateTypeStatus.REJECTED.value: "Reddedildi",
}
DECIDED_NOTES = {
    CandidateTypeStatus.APPROVED.value: "Bu aday tür onaylanmış; yeniden karara bağlanamaz.",
    CandidateTypeStatus.REJECTED.value: "Bu aday tür reddedilmiş; yeniden karara bağlanamaz.",
}
DECIDED_NOTE = "Bu aday tür karara bağlanmış; yeniden karara bağlanamaz."
CANDIDATE_NOTICES = {
    "approved": "Aday tür standart türler arasına eklendi; tür bir sonraki analizden itibaren "
    "geçerlidir. İlişkili Unknown öğeleri aşağıdan toplu yeniden analiz edilebilir.",
    "rejected": "Aday tür reddedildi; bir daha listeye düşmez.",
}
NOT_APPROVED_NOTE = "Toplu yeniden analiz yalnız onaylanmış aday türde yapılır."
NO_RELATED_NOTE = (
    "Bu aday türle ilişkili bekleyen Unknown öğesi yok; yeniden analiz edilecek parti bulunmuyor."
)
# §20.6 dışı (PLAN.md §D30): yeniden analizin onay metinlerinin (D23) çoğulu.
BATCH_REANALYZE_FIRST = "Bu {count} partiyi yeniden analiz etmek üzeresiniz. Emin misiniz?"
BATCH_REANALYZE_SECOND = (
    "Bu işlem her partiye yeni bir plan sürümü açacak; önceki sürümlerin çıktıları "
    '"eski sürüm" olarak işaretlenecektir. Son kararınız mı?'
)


def type_form(
    # Alan adı `slug`; yol parametresiyle (`/document-types/{slug}`) karışmasın diye takma adla.
    type_slug: Annotated[str, Form(alias="slug")] = "",
    name: Annotated[str, Form()] = "",
    file_label: Annotated[str, Form()] = "",
    country: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    expected_file_types: Annotated[list[str] | None, Form()] = None,
    pages_min: Annotated[str, Form()] = "",
    pages_max: Annotated[str, Form()] = "",
    sides: Annotated[str, Form()] = "",
    direct: Annotated[str | None, Form()] = None,
    analyze: Annotated[str | None, Form()] = None,
    required_fields: Annotated[str, Form()] = "",
    allowed_conversions: Annotated[list[str] | None, Form()] = None,
    output_format: Annotated[str, Form()] = "",
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
    prompt_description: Annotated[str, Form()] = "",
) -> TypeForm:
    """Formun kayıt alanları. Başka form alanı okunmaz: `active` ve `photo_rules` bu formdan
    değişmez. İşaret kutusu (`direct`, `analyze`) gönderilmişse işaretlidir."""
    return TypeForm(
        slug=type_slug,
        name=name,
        file_label=file_label,
        country=country,
        description=description,
        expected_file_types=tuple(expected_file_types or ()),
        pages_min=pages_min,
        pages_max=pages_max,
        sides=sides,
        direct=direct is not None,
        analyze=analyze is not None,
        required_fields=required_fields,
        allowed_conversions=tuple(allowed_conversions or ()),
        output_format=output_format,
        acceptance_criteria=tuple(acceptance_criteria or ()),
        prompt_description=prompt_description,
    )


SubmittedForm = Annotated[TypeForm, Depends(type_form)]


def _form_page(
    request: Request,
    user: PanelUser,
    form: TypeForm,
    *,
    slug: str | None,
    problems: dict[str, list[str]] | None = None,
    current_problems: tuple[str, ...] = (),
    status_code: int = status.HTTP_200_OK,
    examples: dict[str, Any] | None = None,
    generated: GeneratedDescription | None = None,
    description_error: str | None = None,
) -> HTMLResponse:
    """Tür formunu çizer. `slug` düzenlenen türdür (yeni türde `None`); `examples` düzenleme
    sayfasının örnek belge bölümünün bağlamıdır (`_examples_context`); `generated` örneklerden
    üretilen (kaydedilmemiş) tür açıklaması, `description_error` üretilemediyse nedeni."""
    return render_page(
        request,
        "catalog_form.html",
        user=user,
        active="document_types",
        status_code=status_code,
        slug=slug,
        current_problems=current_problems,
        **_fields_context(form, problems),
        **(examples or {}),
        generated=generated,
        description_error=description_error,
        script_labels=SCRIPT_LABELS,
        max_description_pages=MAX_DESCRIPTION_PAGES,
        is_new=slug is None,
    )


def _size_label(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{max(1, round(size / 1024))} KB"


def _examples_context(
    layout: DataLayout,
    slug: str,
    *,
    stored: list[StoredExample] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Düzenleme sayfasındaki örnek belge bölümünün bağlamı: türün örnekleri (dosya sistemi,
    veritabanı değil), bu yüklemenin sonucu ve hataları."""
    return {
        "examples": [
            {"name": item.name, "size_label": _size_label(item.size)}
            for item in list_examples(layout, slug)
        ],
        "example_stored": stored or [],
        "example_errors": errors or [],
    }


def _fields_context(form: TypeForm, problems: dict[str, list[str]] | None) -> dict[str, Any]:
    """`catalog_type_fields.html`'in bağlamı (`is_new` hariç); madde listesinin sonuna
    JavaScript'siz ekleme için boş bir alan konur."""
    return {
        "form": form,
        "problems": problems or {},
        "criteria": [*form.acceptance_criteria, ""],
        "file_types": FILE_TYPE_LABELS,
        "sides_options": SIDES_LABELS,
        "conversions": CONVERSION_LABELS,
        "output_formats": OUTPUT_FORMAT_LABELS,
    }


def _redirect(notice: str, slug: str) -> RedirectResponse:
    return RedirectResponse(
        f"{LIST_PATH}?{urlencode({'notice': notice, 'slug': slug})}", status.HTTP_303_SEE_OTHER
    )


@router.get(LIST_PATH, response_class=HTMLResponse)
def catalog_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    notice: Annotated[str | None, Query(max_length=32)] = None,
    slug: Annotated[str | None, Query(max_length=64)] = None,
) -> HTMLResponse:
    types = list_types(session)
    named = {item.slug: item.name for item in types}
    notice_text = NOTICES.get(notice or "")
    if notice_text and slug in named:
        notice_text = f"{named[slug]}: {notice_text}"
    return render_page(
        request,
        "catalog.html",
        user=user,
        active="document_types",
        entry=MENU_BY_KEY["document_types"],
        types=types,
        notice_text=notice_text,
        sides_labels=SIDES_LABELS,
        pending_candidates=count_pending_candidate_types(session),
    )


@router.get(f"{LIST_PATH}/new", response_class=HTMLResponse)
def new_type_page(request: Request, user: CurrentUser) -> HTMLResponse:
    return _form_page(request, user, TypeForm(), slug=None)


# `/document-types/{slug}`'dan önce kayıtlı olmalı: yol tek parçadır.
@router.get(CANDIDATES_PATH, response_class=HTMLResponse)
def candidate_types_page(
    request: Request,
    user: CurrentUser,
    session: DbSession,
    notice: Annotated[str | None, Query(max_length=32)] = None,
) -> HTMLResponse:
    """11.5.1 — bekleyen aday türler adı, görülme sayısı ve örnek sayfalarıyla; onaylanmış ama
    ilişkili Unknown öğesi bekleyen adaylar ayrıca (toplu yeniden analiz için, 11.5.3)."""
    pending = list_candidate_types(session)
    approved = list_candidate_types(session, CandidateTypeStatus.APPROVED, sample_limit=0)
    related = _related_by_candidate(session, [item.id for item in (*pending, *approved)])
    response = render_page(
        request,
        "catalog_candidates.html",
        user=user,
        active="document_types",
        pending=pending,
        approved=[item for item in approved if related[item.id]],
        related_counts={key: len(items) for key, items in related.items()},
        notice_text=CANDIDATE_NOTICES.get(notice or ""),
    )
    # Okuma işlemi de SQLite'ta yazma kilidini tutar (`app.db.session`).
    session.rollback()
    return response


@router.post(LIST_PATH, response_class=HTMLResponse)
def create_type_endpoint(
    request: Request, user: CurrentUser, session: DbSession, form: SubmittedForm
) -> Response:
    try:
        entry = build_entry(form)
    except TypeFormError as exc:
        return _form_page(
            request,
            user,
            form,
            slug=None,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        create_type(session, entry)
        session.commit()
    except TypeExistsError:
        session.rollback()
        return _form_page(
            request,
            user,
            form,
            slug=None,
            problems={"slug": [SLUG_TAKEN]},
            status_code=status.HTTP_409_CONFLICT,
        )
    return _redirect("created", entry.slug)


@router.get(f"{LIST_PATH}/{{slug}}", response_class=HTMLResponse)
def type_page(
    slug: str, request: Request, user: CurrentUser, session: DbSession, layout: Layout
) -> HTMLResponse:
    try:
        record = load_record(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    # Kayıtlı tür §8.6'ya uymuyorsa (elle değiştirilmiş satır) form yine açılır; kaydetmek
    # onu düzeltir.
    return _form_page(
        request,
        user,
        TypeForm.from_record(record),
        slug=slug,
        current_problems=record_problems(record),
        examples=_examples_context(layout, slug),
    )


@router.post(f"{LIST_PATH}/{{slug}}", response_class=HTMLResponse)
def update_type_endpoint(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    form: SubmittedForm,
) -> Response:
    # Slug adresten gelir, formdan değil: değişmez (belgeler ve çıktı adları ona bağlı).
    form = replace(form, slug=slug)
    try:
        load_record(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    try:
        entry = build_entry(form)
    except TypeFormError as exc:
        return _form_page(
            request,
            user,
            form,
            slug=slug,
            problems=exc.problems,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            examples=_examples_context(layout, slug),
        )
    try:
        update_type(session, entry)
        session.commit()
    except TypeNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    return _redirect("updated", slug)


def _set_active(session: Session, slug: str, active: bool) -> RedirectResponse:
    try:
        set_type_active(session, slug, active)
        session.commit()
    except TypeNotFoundError:
        session.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    return _redirect("activated" if active else "deactivated", slug)


@router.post(f"{LIST_PATH}/{{slug}}/deactivate")
def deactivate_type(slug: str, session: DbSession) -> RedirectResponse:
    return _set_active(session, slug, False)


@router.post(f"{LIST_PATH}/{{slug}}/activate")
def activate_type(slug: str, session: DbSession) -> RedirectResponse:
    return _set_active(session, slug, True)


def _known_type(session: Session, slug: str) -> dict[str, Any]:
    """Türün ham kaydı; katalogda yoksa 404. Örnek uçları yalnız katalogdaki türlerindir. Okuma
    SQLite'ta yazma kilidini tutar (`app.db.session`): işlem hemen bırakılır."""
    try:
        return load_record(session, slug)
    except TypeNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, TYPE_NOT_FOUND) from None
    finally:
        session.rollback()


@router.post(f"{LIST_PATH}/{{slug}}/examples", response_class=HTMLResponse)
async def upload_examples(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    settings: AppSettings,
) -> HTMLResponse:
    """11.2.1 — türe bir ya da birkaç örnek belge yükler. Dosyalar diske yazılmadan önce hep
    birlikte denetlenir: biri reddedilirse hiçbiri yazılmaz (422). Veritabanına hiçbir şey
    yazılmaz; örnek çalışan verisi değildir."""
    record = _known_type(session, slug)
    # Form elle okunur: tarayıcı dosya seçilmemişken adı boş tek bir parça gönderir (bkz.
    # `submit_upload`). Her dosya sınırın bir baytı ötesine kadar okunur: devasa dosya belleğe
    # tümüyle alınmaz, sınır aşımı yine yakalanır.
    limit = settings.max_upload_file_size_bytes
    async with request.form() as submitted:
        chosen = [
            (file.filename, await file.read(limit + 1))
            for file in submitted.getlist("files")
            if isinstance(file, StarletteUploadFile) and file.filename
        ]

    errors: list[str] = []
    checked = []
    for name, content in chosen:
        try:
            checked.append((name, content, check_example(name, content, max_bytes=limit)))
        except ExampleRejectedError as exc:
            errors.append(str(exc))
    if not chosen:
        errors.append(NO_EXAMPLE_FILE)
    if errors:
        return _form_page(
            request,
            user,
            TypeForm.from_record(record),
            slug=slug,
            current_problems=record_problems(record),
            status_code=(
                status.HTTP_422_UNPROCESSABLE_CONTENT if chosen else status.HTTP_400_BAD_REQUEST
            ),
            examples=_examples_context(layout, slug, errors=errors),
        )
    stored = [store_example(layout, slug, name, content, kind) for name, content, kind in checked]
    return _form_page(
        request,
        user,
        TypeForm.from_record(record),
        slug=slug,
        current_problems=record_problems(record),
        examples=_examples_context(layout, slug, stored=stored),
    )


@router.get(f"{LIST_PATH}/{{slug}}/examples/{{name}}")
def example_file(slug: str, name: str, session: DbSession, layout: Layout) -> FileResponse:
    """Türün örnek dosyası (yüklendiği baytlar). Tür katalogda ya da dosya türün örnek dizininde
    yoksa 404."""
    _known_type(session, slug)
    path = example_path(layout, slug, name)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, EXAMPLE_NOT_FOUND)
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})


def get_description_provider(settings: AppSettings) -> AnalysisProvider | ProviderConfigError:
    """Tür açıklamasının (11.3.1) sağlayıcısı; kurulamazsa nedenini taşıyan hata (kullanıcıya
    gösterilir)."""
    try:
        return create_provider(settings)
    except ProviderConfigError as exc:
        return exc


DescriptionProvider = Annotated[
    AnalysisProvider | ProviderConfigError, Depends(get_description_provider)
]


@router.post(f"{LIST_PATH}/{{slug}}/description", response_class=HTMLResponse)
def generate_description(
    slug: str,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Layout,
    settings: AppSettings,
    form: SubmittedForm,
    provider: DescriptionProvider,
) -> HTMLResponse:
    """11.3.1 — türün örneklerinden yapılandırılmış açıklama üretir ve metnini formun
    `prompt_description` alanına yazarak formu yeniden çizer. **Kaydetmez:** İK düzenleyip kaydeder.

    Formdaki (kaydedilmemiş) değerler korunur ve açıklama onlarla istenir. Veritabanı işlemi
    sağlayıcı çağrısından önce bırakılır (`_known_type`): uzun süren çağrı yazma kilidi tutmaz.
    """
    form = replace(form, slug=slug)
    record = _known_type(session, slug)

    def page(
        status_code: int,
        *,
        problems: dict[str, list[str]] | None = None,
        generated: GeneratedDescription | None = None,
        error: str | None = None,
    ) -> HTMLResponse:
        shown = form if generated is None else replace(form, prompt_description=generated.text)
        return _form_page(
            request,
            user,
            shown,
            slug=slug,
            problems=problems,
            current_problems=record_problems(record),
            status_code=status_code,
            examples=_examples_context(layout, slug),
            generated=generated,
            description_error=error,
        )

    try:
        entry = build_entry(form)
    except TypeFormError as exc:
        return page(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            problems=exc.problems,
            error=DESCRIPTION_INVALID_FORM,
        )
    if isinstance(provider, ProviderConfigError):
        return page(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            error=DESCRIPTION_PROVIDER_UNAVAILABLE.format(detail=provider),
        )
    try:
        generated = describe_type(entry, layout, settings, provider)
    except TypeNotAnalyzedError:
        return page(status.HTTP_422_UNPROCESSABLE_CONTENT, error=DESCRIPTION_NOT_ANALYZED)
    except NoExamplePagesError as exc:
        error = " ".join((DESCRIPTION_NO_EXAMPLES, *exc.skipped))
        return page(status.HTTP_422_UNPROCESSABLE_CONTENT, error=error)
    except ProviderError as exc:
        return page(
            status.HTTP_502_BAD_GATEWAY, error=DESCRIPTION_PROVIDER_FAILED.format(detail=exc)
        )
    except TypeDescriptionError:
        return page(status.HTTP_502_BAD_GATEWAY, error=DESCRIPTION_REJECTED)
    return page(status.HTTP_200_OK, generated=generated)


def _criteria_fragment(request: Request, user: PanelUser, items: list[str]) -> HTMLResponse:
    return render_page(request, "catalog_criteria.html", user=user, criteria=items)


@router.post(f"{LIST_PATH}/criteria/add", response_class=HTMLResponse)
def add_criterion(
    request: Request,
    user: CurrentUser,
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    """Madde listesine boş bir madde ekler; kaydetmez (formun geri kalanı yerinde durur)."""
    return _criteria_fragment(request, user, [*(acceptance_criteria or ()), ""])


@router.post(f"{LIST_PATH}/criteria/remove", response_class=HTMLResponse)
def remove_criterion(
    request: Request,
    user: CurrentUser,
    index: Annotated[int, Form(ge=0)],
    acceptance_criteria: Annotated[list[str] | None, Form()] = None,
) -> HTMLResponse:
    """`index`teki maddeyi listeden çıkarır; kaydetmez."""
    items = list(acceptance_criteria or ())
    if index < len(items):
        del items[index]
    return _criteria_fragment(request, user, items)


# --- 11.5: aday türler ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RelatedItemView:
    """Aday türle ilişkili bekleyen Unknown öğesi (kuyruk öğesi detayına bağlanır)."""

    id: int
    upload_id: str
    source: str


@dataclass(frozen=True, slots=True)
class ReanalysisTargetView:
    """Toplu yeniden analizde yeniden analiz edilecek parti ve onun güncel plan sürümü."""

    upload_id: str
    version: int
    item_count: int


@dataclass(frozen=True, slots=True)
class ReanalyzedView:
    """Toplu yeniden analizin bir partideki sonucu."""

    upload_id: str
    previous_version: int
    version: int
    superseded: int


def _first_page(item: QueueItem) -> tuple[int, int] | None:
    """Öğenin ilk kaynak sayfası `(dosya kimliği, 0 tabanlı sıra)`; kayıt bozuk ya da sayfasızsa
    `None` (öğe hiçbir adayla ilişkilendirilmez)."""
    refs = _payload_refs(item.payload_json)
    parsed = _reference(refs[0]) if refs else None
    if parsed is None or not parsed[1]:
        return None
    return parsed[0], parsed[1][0]


def _related_by_candidate(session: Session, candidate_ids: list[int]) -> dict[int, list[QueueItem]]:
    """11.5.3 — her adayın ilişkili bekleyen Unknown öğeleri (kuyruk sırasıyla). Bekleyen öğe
    kuyruk ekranlarının tanımıdır (`_state_filter`): çözülmemiş ve partisinin güncel planında."""
    if not candidate_ids:
        return {}
    unknown = session.scalars(
        select(QueueItem)
        .where(QueueItem.kind == QueueKind.UNKNOWN.value, _state_filter(QueueState.OPEN))
        .order_by(QueueItem.id)
    ).all()
    firsts = [(item, _first_page(item)) for item in unknown]
    related: dict[int, list[QueueItem]] = {}
    for candidate_id in candidate_ids:
        refs = sample_page_refs(session, session.get_one(CandidateDocumentType, candidate_id))
        related[candidate_id] = [item for item, first in firsts if first in refs]
    return related


def _related_view(session: Session, item: QueueItem) -> RelatedItemView:
    refs = _payload_refs(item.payload_json)
    parsed = _reference(refs[0]) if refs else None
    assert parsed is not None  # `_first_page` ile ilişkilendirilmiş öğe
    file_id, pages = parsed
    # İlk sayfa adayın örnek sayfalarından biridir: dosyası vardır.
    name = session.get_one(UploadFile, file_id).original_name
    return RelatedItemView(item.id, item.upload_id, f"{name} · {_page_ranges(pages)}")


def _reanalysis_targets(session: Session, items: list[QueueItem]) -> list[tuple[Upload, Plan, int]]:
    """İlişkili öğelerin partileri (kimlik sırasıyla), güncel planları ve partideki öğe sayısı.
    Süren partide yeniden analiz yapılmaz (10.3.2): biri sürüyorsa 409 ve hiçbiri."""
    counts = Counter(item.upload_id for item in items)
    targets = []
    for upload_id in sorted(counts):
        upload = session.get_one(Upload, upload_id)
        if UploadStatus(upload.status) not in FINAL_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{upload_id}: {BUSY_MESSAGE}")
        plan = current_plan(session, upload)
        assert plan is not None  # bekleyen öğe partinin güncel planındadır
        targets.append((upload, plan, counts[upload_id]))
    return targets


def _target_views(targets: list[tuple[Upload, Plan, int]]) -> list[ReanalysisTargetView]:
    return [ReanalysisTargetView(upload.id, plan.version, count) for upload, plan, count in targets]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def approval_subject(candidate_id: int, entry: CatalogEntry) -> str:
    """Tür onayı belirtecinin (`Operation.APPROVE_TYPE`) bağlı olduğu hedef: aday + eklenecek
    kaydın özeti. İkinci onaydan sonra kayıtta bir alan değişirse belirteç geçmez."""
    canonical = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return f"{candidate_id}:{_digest(canonical)}"


def batch_reanalysis_subject(candidate_id: int, targets: list[tuple[Upload, Plan, int]]) -> str:
    """Toplu yeniden analiz belirtecinin (`Operation.REANALYZE`) hedefi: aday + partiler ve güncel
    planları. Parti kümesi ya da bir partinin planı değişmişse belirteç geçmez."""
    plans = ";".join(f"{upload.id}:{plan.id}" for upload, plan, _ in targets)
    return f"candidate-types:{candidate_id}:{_digest(plans)}"


def _decided_note(candidate_status: str) -> str:
    return DECIDED_NOTES.get(candidate_status, DECIDED_NOTE)


def _candidate_or_404(session: Session, candidate_id: int) -> CandidateDocumentType:
    try:
        return load_candidate_type(session, candidate_id)
    except CandidateNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, CANDIDATE_NOT_FOUND) from None


def _candidate_page(
    request: Request,
    user: PanelUser,
    session: Session,
    candidate: CandidateDocumentType,
    *,
    form: TypeForm | None = None,
    problems: dict[str, list[str]] | None = None,
    notice: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Aday türün detayı: örnek sayfalar, ilişkili bekleyen Unknown öğeleri ve durumuna göre onay
    formu + ret (bekleyen), toplu yeniden analiz (onaylanmış) ya da ret notu."""
    (summary,) = summarize_candidates(session, [candidate], sample_limit=DETAIL_SAMPLE_LIMIT)
    related = _related_by_candidate(session, [candidate.id])[candidate.id]
    pending = candidate.status == CandidateTypeStatus.PENDING.value
    approved = candidate.status == CandidateTypeStatus.APPROVED.value
    targets: list[ReanalysisTargetView] = []
    blocked = None
    if approved and related:
        try:
            targets = _target_views(_reanalysis_targets(session, related))
        except HTTPException as exc:
            blocked = str(exc.detail)
    context: dict[str, Any] = {}
    if pending:
        context = _fields_context(form or suggested_form(candidate), problems)
    return render_page(
        request,
        "catalog_candidate.html",
        user=user,
        active="document_types",
        status_code=status_code,
        candidate=summary,
        status=candidate.status,
        status_label=CANDIDATE_STATUS_LABELS.get(candidate.status, candidate.status),
        approved_slug=approved_type_slug(session, candidate.id) if approved else None,
        related=[_related_view(session, item) for item in related],
        targets=targets,
        reanalysis_blocked=blocked,
        reanalysis_first=BATCH_REANALYZE_FIRST.format(count=len(targets)),
        notice_text=notice,
        is_new=True,
        **context,
    )


def _step_page(
    request: Request, user: PanelUser, candidate_id: int, status_code: int, **context: object
) -> HTMLResponse:
    """Onay ve yeniden analiz adımlarının sayfası (`catalog_candidate_step.html`): onay metni,
    sonuç ya da hata."""
    return render_page(
        request,
        "catalog_candidate_step.html",
        user=user,
        active="document_types",
        status_code=status_code,
        candidate_id=candidate_id,
        **context,
    )


@router.get(f"{CANDIDATES_PATH}/{{candidate_id}}", response_class=HTMLResponse)
def candidate_type_page(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    notice: Annotated[str | None, Query(max_length=32)] = None,
) -> HTMLResponse:
    candidate = _candidate_or_404(session, candidate_id)
    response = _candidate_page(
        request, user, session, candidate, notice=CANDIDATE_NOTICES.get(notice or "")
    )
    session.rollback()
    return response


# --- 11.5.2: onay -------------------------------------------------------------------------------


def _entry_rows(entry: CatalogEntry) -> list[tuple[str, str]]:
    """Onay adımlarında gösterilen, kataloğa eklenecek kayıt."""
    pages = entry.expected_pages
    return [
        ("Slug", entry.slug),
        ("Ad", entry.name),
        ("Dosya etiketi", entry.file_label),
        ("Ülke", entry.country or "—"),
        ("Açıklama", entry.description or "—"),
        (
            "Beklenen dosya türleri",
            ", ".join(FILE_TYPE_LABELS[t] for t in entry.expected_file_types),
        ),
        ("Beklenen sayfa sayısı", "—" if pages is None else f"{pages.min} – {pages.max}"),
        ("Yüz yapısı", SIDES_LABELS[entry.sides]),
        ("Direkt Belge", "Evet" if entry.direct else "Hayır"),
        ("Analiz", "Evet" if entry.analyze else "Hayır"),
        ("Zorunlu alanlar", ", ".join(entry.required_fields) or "—"),
        (
            "İzinli dönüşümler",
            ", ".join(CONVERSION_LABELS[c] for c in entry.allowed_conversions) or "—",
        ),
        ("Çıktı biçimi", OUTPUT_FORMAT_LABELS[entry.output_format]),
        ("Kabul kriterleri", " · ".join(entry.acceptance_criteria) or "—"),
        ("Analizci için açıklama", entry.prompt_description or "—"),
    ]


def _approval(
    session: Session, candidate_id: int, form: TypeForm
) -> tuple[CandidateDocumentType, CatalogEntry]:
    """Onay adımlarının ortak denetimi: aday (404), bekliyor mu (409), form (`TypeFormError`) ve
    slug katalogda boş mu (`TypeExistsError`)."""
    candidate = _candidate_or_404(session, candidate_id)
    if candidate.status != CandidateTypeStatus.PENDING.value:
        raise HTTPException(status.HTTP_409_CONFLICT, _decided_note(candidate.status))
    entry = build_entry(form)
    if session.get(KnownDocumentType, entry.slug) is not None:
        raise TypeExistsError(entry.slug)
    return candidate, entry


def _approval_refused(
    request: Request,
    user: PanelUser,
    session: Session,
    candidate_id: int,
    form: TypeForm,
    exc: Exception,
) -> HTMLResponse:
    """Onay adımının reddi: aday yok/karara bağlanmış → hata sayfası; form ya da slug → detay
    sayfası, form girilen değerlerle ve alan başına mesajla (hiçbir şey yazılmadı)."""
    if isinstance(exc, HTTPException):
        return _step_page(request, user, candidate_id, exc.status_code, error=str(exc.detail))
    if isinstance(exc, TypeFormError):
        problems, code = exc.problems, status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        problems, code = {"slug": [SLUG_TAKEN]}, status.HTTP_409_CONFLICT
    candidate = session.get_one(CandidateDocumentType, candidate_id)
    return _candidate_page(
        request, user, session, candidate, form=form, problems=problems, status_code=code
    )


def _approval_step(candidate: CandidateDocumentType, entry: CatalogEntry) -> dict[str, object]:
    # Onay adımlarının ortak içeriği: eklenecek kayıt ve bir sonraki adıma taşınan (doğrulanmış)
    # form değerleri.
    return {
        "step": "approve",
        "candidate_name": candidate.proposed_name,
        "rows": _entry_rows(entry),
        "form": TypeForm.from_record(entry.model_dump(mode="json")),
    }


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/approve/confirm", response_class=HTMLResponse)
def approval_first_confirmation(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    form: SubmittedForm,
) -> HTMLResponse:
    """11.5.2 — formu doğrular ve §20.6'nın birinci onay metnini verir; hiçbir şey değişmez."""
    try:
        candidate, entry = _approval(session, candidate_id, form)
        response = _step_page(
            request,
            user,
            candidate_id,
            status.HTTP_200_OK,
            first_confirmation=first_text(Operation.APPROVE_TYPE, type_name=entry.name),
            **_approval_step(candidate, entry),
        )
    except (HTTPException, TypeFormError, TypeExistsError) as exc:
        response = _approval_refused(request, user, session, candidate_id, form, exc)
    session.rollback()
    return response


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/approve/prepare", response_class=HTMLResponse)
def prepare_approval(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    form: SubmittedForm,
) -> HTMLResponse:
    """11.5.2 — birinci onaydan sonra ikinci onay metnini ve kayda bağlı tek kullanımlık onay
    belirtecini verir (§20.6.1)."""
    try:
        candidate, entry = _approval(session, candidate_id, form)
        issued = issue_confirmation(
            session, request, user, Operation.APPROVE_TYPE, approval_subject(candidate_id, entry)
        )
    except (HTTPException, TypeFormError, TypeExistsError) as exc:
        session.rollback()
        response = _approval_refused(request, user, session, candidate_id, form, exc)
        session.rollback()
        return response
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, status.HTTP_400_BAD_REQUEST, error=str(exc))
    session.commit()
    return _step_page(
        request,
        user,
        candidate_id,
        status.HTTP_200_OK,
        second_confirmation=second_text(Operation.APPROVE_TYPE),
        confirmation=issued.token,
        **_approval_step(candidate, entry),
    )


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/approve", response_class=HTMLResponse)
def approve_candidate(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    form: SubmittedForm,
    confirmation: Annotated[str | None, Form()] = None,
) -> Response:
    """11.5.2 — ikinci onayın belirteciyle türü kataloğa ekler ve adayı onaylar (K16).

    Belirteç yoksa, süresi geçmişse, kullanılmışsa ya da başka adaya, başka kayda, işleme veya
    oturuma aitse hiçbir şey yapılmaz (400). Belirtecin tüketilmesi, `USER_CONFIRMED`, türün
    eklenmesi ve `TYPE_APPROVED` tek işlemdedir: biri düşerse hiçbiri yazılmaz.
    """
    try:
        candidate, entry = _approval(session, candidate_id, form)
        # §20.6.1: belirteç tüketilir ve `USER_CONFIRMED` (kullanıcı adı, işlem, hedef, iki onayın
        # zamanı) yazılır, ardından işlemin kendi olayı (`TYPE_APPROVED`) düşer.
        confirm_operation(
            session,
            request,
            user,
            Operation.APPROVE_TYPE,
            approval_subject(candidate_id, entry),
            confirmation,
            event_target={"candidate_type_id": candidate.id, "document_type_slug": entry.slug},
        )
        approve_candidate_type(session, candidate_id, entry, actor=user.username)
    except (HTTPException, TypeFormError, TypeExistsError) as exc:
        session.rollback()
        response = _approval_refused(request, user, session, candidate_id, form, exc)
        session.rollback()
        return response
    except ConfirmationRefusedError:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_400_BAD_REQUEST, error=CONFIRMATION_REFUSED
        )
    except CandidateDecidedError as exc:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_409_CONFLICT, error=_decided_note(exc.status)
        )
    session.commit()
    return RedirectResponse(
        f"{CANDIDATES_PATH}/{candidate_id}?notice=approved", status.HTTP_303_SEE_OTHER
    )


# --- 11.5.4: ret --------------------------------------------------------------------------------


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/reject", response_class=HTMLResponse)
def reject_candidate(
    candidate_id: int, request: Request, user: CurrentUser, session: DbSession
) -> Response:
    """11.5.4 — adayı reddeder (`TYPE_REJECTED`, kullanıcı adıyla); reddedilen aday bir daha
    listeye düşmez. Katalog ve belgeler değişmez."""
    try:
        reject_candidate_type(session, candidate_id, actor=user.username)
    except CandidateNotFoundError:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_404_NOT_FOUND, error=CANDIDATE_NOT_FOUND
        )
    except CandidateDecidedError as exc:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_409_CONFLICT, error=_decided_note(exc.status)
        )
    session.commit()
    return RedirectResponse(f"{CANDIDATES_PATH}?notice=rejected", status.HTTP_303_SEE_OTHER)


# --- 11.5.3: toplu yeniden analiz ---------------------------------------------------------------


def _reanalysis(
    session: Session, candidate_id: int
) -> tuple[CandidateDocumentType, list[tuple[Upload, Plan, int]]]:
    """Toplu yeniden analizin ortak denetimi: aday (404), onaylanmış mı (409), ilişkili bekleyen
    Unknown öğesi var mı (409) ve partilerin hiçbiri sürmüyor mu (409)."""
    candidate = _candidate_or_404(session, candidate_id)
    if candidate.status != CandidateTypeStatus.APPROVED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_APPROVED_NOTE)
    related = _related_by_candidate(session, [candidate.id])[candidate.id]
    if not related:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_RELATED_NOTE)
    return candidate, _reanalysis_targets(session, related)


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/reanalyze/prepare", response_class=HTMLResponse)
def prepare_batch_reanalysis(
    candidate_id: int, request: Request, user: CurrentUser, session: DbSession
) -> HTMLResponse:
    """11.5.3 — birinci onaydan sonra ikinci onay metnini ve partilere bağlı tek kullanımlık
    belirteci verir (10.3.2, §20.6.1)."""
    try:
        candidate, targets = _reanalysis(session, candidate_id)
        issued = issue_confirmation(
            session,
            request,
            user,
            Operation.REANALYZE,
            batch_reanalysis_subject(candidate_id, targets),
        )
    except HTTPException as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, exc.status_code, error=str(exc.detail))
    except ConfirmationRefusedError as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, status.HTTP_400_BAD_REQUEST, error=str(exc))
    session.commit()
    return _step_page(
        request,
        user,
        candidate_id,
        status.HTTP_200_OK,
        step="reanalyze",
        candidate_name=candidate.proposed_name,
        targets=_target_views(targets),
        second_confirmation=BATCH_REANALYZE_SECOND,
        confirmation=issued.token,
    )


@router.post(f"{CANDIDATES_PATH}/{{candidate_id}}/reanalyze", response_class=HTMLResponse)
def batch_reanalyze(
    candidate_id: int,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    layout: Annotated[DataLayout, Depends(get_layout)],
    executor: Annotated[PlanExecutor, Depends(get_plan_executor)],
    provider: ReanalysisProvider,
    confirmation: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    """11.5.3 — ikinci onayın belirteciyle ilişkili Unknown öğelerinin partilerini güncel katalogla
    yeniden analiz eder (06.6.2, K18).

    Belirteçsiz ya da geçersiz belirteçle hiçbir şey yapılmaz (400). Belirtecin tüketilmesi,
    `USER_CONFIRMED` ve bütün partilerin yeniden analizi tek işlemdedir: biri düşerse hiçbiri
    kalmaz.
    """
    try:
        candidate, targets = _reanalysis(session, candidate_id)
        confirm_operation(
            session,
            request,
            user,
            Operation.REANALYZE,
            batch_reanalysis_subject(candidate_id, targets),
            confirmation,
            event_target={
                "candidate_type_id": candidate.id,
                "uploads": [
                    {"upload_id": upload.id, "plan_id": plan.id} for upload, plan, _ in targets
                ],
            },
        )
        if isinstance(provider, ProviderConfigError):
            raise ReanalysisProviderError(str(provider))
        catalog = export_catalog(session)
        results = []
        for upload, _, _ in targets:
            reanalysis = reanalyze_upload(
                session, layout, upload, provider=provider, catalog=catalog, executor=executor
            )
            results.append(
                ReanalyzedView(
                    upload.id,
                    reanalysis.previous_plan.version,
                    reanalysis.plan.version,
                    len(reanalysis.superseded_document_ids),
                )
            )
    except HTTPException as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, exc.status_code, error=str(exc.detail))
    except ConfirmationRefusedError:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_400_BAD_REQUEST, error=CONFIRMATION_REFUSED
        )
    except ReanalysisProviderError as exc:
        session.rollback()
        return _step_page(
            request, user, candidate_id, status.HTTP_503_SERVICE_UNAVAILABLE, error=str(exc)
        )
    except PLAN_EXECUTION_ERRORS as exc:
        session.rollback()
        return _step_page(request, user, candidate_id, status.HTTP_409_CONFLICT, error=str(exc))
    session.commit()
    remaining = len(_related_by_candidate(session, [candidate_id])[candidate_id])
    session.rollback()
    return _step_page(
        request,
        user,
        candidate_id,
        status.HTTP_200_OK,
        step="reanalyzed",
        candidate_name=candidate.proposed_name,
        results=results,
        remaining=remaining,
    )
