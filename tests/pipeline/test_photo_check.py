"""11.7.1 — profil fotoğrafı analizde katalogda açık kurallara göre değerlendirilir: her kural
`pass`/`fail`/`unsure`, asgari çözünürlük kaynaktan deterministik ölçülür, sonuç sayfaya saklanır;
11.7.2 — kontrol fotoğrafı ve kaynağını değiştirmez.

Sağlayıcı ağ çağrısı yapmaz (sıralı kayıtlı yanıt); fotoğraflar `tests/fixtures/gen.py`'nin sentetik
siluetleridir (gerçek kişi yok). Planın hükmü (`fail` → Unresolved) `test_plan.py`'de, uçtan uca
akış `tests/test_scenarios_s01_s05.py`'dedir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import (
    AnalysisProvider,
    PageAnalysisRequest,
    PhotoCheck,
    PhotoCheckRequest,
    PhotoRuleResult,
    ProviderConnectionError,
    build_page_analysis_instructions,
)
from app.ai.prompts import load_photo_check_instructions
from app.catalog import Catalog, enabled_photo_rules, load_seed_catalog, validate_catalog
from app.config import Settings
from app.db.models import Event, Page, Upload, UploadFile, UploadStatus
from app.events import EventType
from app.pipeline.analyze import (
    PageAnalysisStatus,
    analyze_upload,
    build_photo_check_prompt,
)
from app.pipeline.render import (
    RenderError,
    mark_upload_file_single_image_pages,
    photo_pixel_size,
    render_image_file,
    render_upload_file,
)
from app.storage import DataLayout, FileKind, detect_file_kind, write_to_inbox
from tests.ai.payloads import analysis_payload
from tests.fixtures.gen import (
    ASKED_PHOTO_RULES,
    make_document_pdf_bytes,
    make_half_filled_image_bytes,
    make_portrait_image_bytes,
    make_text_pdf_bytes,
    photo_check_response,
    profile_picture_page,
)

CATALOG = load_seed_catalog()
UPLOAD_ID = "u_20260919_0081"
PHOTO = "profile_picture"
CATALOG_ORDER = [rule.id for rule in enabled_photo_rules(None)]


def _settings() -> Settings:
    return Settings(_env_file=None, database_url="sqlite://")


def _catalog(photo_rules: dict[str, Any] | None) -> Catalog:
    entries = [entry.model_dump(mode="json") for entry in CATALOG]
    for entry in entries:
        if entry["slug"] == PHOTO:
            entry["photo_rules"] = photo_rules
    return validate_catalog(entries)


def _upload(session: Session, layout: DataLayout, *files: tuple[str, bytes]) -> Upload:
    """Partiyi Inbox'a yazar ve sayfaları gerçek render adımlarıyla üretir."""
    upload = Upload(id=UPLOAD_ID, channel="web", status=UploadStatus.ANALYZING.value)
    session.add(upload)
    for name, content in files:
        stored = write_to_inbox(layout, upload.id, name, content)
        upload_file = UploadFile(
            upload=upload,
            original_name=name,
            stored_path=stored.path.relative_to(layout.root).as_posix(),
            sha256=stored.sha256,
            mime="application/octet-stream",
        )
        session.add(upload_file)
        session.flush()
        if detect_file_kind(content) is FileKind.PDF:
            render_upload_file(session, layout, _settings(), upload_file)
            mark_upload_file_single_image_pages(session, layout, upload_file)
        else:
            render_image_file(session, layout, _settings(), upload_file)
    session.flush()
    return upload


class Scripted(AnalysisProvider):
    """Sayfa analizi ve fotoğraf kontrolü isteklerine tek sıradan yanıt verir; hata örneği
    fırlatılır."""

    name = "scripted"

    def __init__(self, *script: object) -> None:
        super().__init__(model="scripted-model")
        self._script = list(script)
        self.requests: list[PageAnalysisRequest] = []
        self.photo_requests: list[PhotoCheckRequest] = []

    def _request_analysis(self, request: PageAnalysisRequest) -> object:
        self.requests.append(request)
        return self._next()

    def _request_photo_check(self, request: PhotoCheckRequest) -> object:
        self.photo_requests.append(request)
        return self._next()

    def _next(self) -> object:
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _photo(page_index: int = 0, **top: Any) -> dict[str, Any]:
    analysis = profile_picture_page().analysis(page_index)
    analysis.update(top)
    return analysis


def _analyze(
    session: Session,
    layout: DataLayout,
    upload: Upload,
    provider: AnalysisProvider,
    catalog: Catalog = CATALOG,
) -> Any:
    instructions = build_page_analysis_instructions(catalog)
    return analyze_upload(session, layout, upload, provider=provider, instructions=instructions)


def _events(session: Session, event_type: EventType) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.type == event_type).order_by(Event.id)))


def _page(upload: Upload, file_number: int = 0) -> Page:
    return upload.files[file_number].pages[0]


# --- 11.7.1: her açık kural değerlendirilir, sonuç sayfaya saklanır -----------------------------


def test_photo_page_is_checked_against_every_open_rule_and_the_result_is_stored(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    provider = Scripted(_photo(), photo_check_response({"plain_background": "unsure"}))

    result = _analyze(session, layout, upload, provider)

    (outcome,) = result.outcomes
    page = _page(upload)
    check = outcome.photo_check
    assert check is not None
    assert [verdict.rule for verdict in check.rules] == CATALOG_ORDER
    assert {verdict.rule: verdict.result for verdict in check.rules} == {
        "face_visible": PhotoRuleResult.PASS,
        "single_person": PhotoRuleResult.PASS,
        "neutral_expression": PhotoRuleResult.PASS,
        "plain_background": PhotoRuleResult.UNSURE,
        "min_resolution": PhotoRuleResult.PASS,
        "no_sunglasses": PhotoRuleResult.PASS,
    }
    resolution = check.verdict("min_resolution")
    assert resolution is not None
    assert resolution.note == "480×600 piksel; asgari 400×400."
    assert page.analysis_status == PageAnalysisStatus.DONE
    assert page.photo_check_json == check.model_dump(mode="json")
    assert PhotoCheck.model_validate(page.photo_check_json) == check
    (event,) = _events(session, EventType.PAGE_ANALYZED)
    assert event.data_json["photo_check"] == {
        verdict.rule: verdict.result.value for verdict in check.rules
    }
    # Olay yalnız kural → sonuç taşır; notlar sayfanın kaydındadır.
    assert "Arka plan" not in str(event.data_json)


def test_photo_check_request_asks_the_open_rules_but_not_the_measured_one(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    provider = Scripted(_photo(), photo_check_response())

    _analyze(session, layout, upload, provider)

    (page_request,) = provider.requests
    (request,) = provider.photo_requests
    assert request.rules == ASKED_PHOTO_RULES
    assert "min_resolution" not in request.rules
    # Sağlayıcıya yalnız işlenen sayfanın analiz görüntüsü gider (CONVENTIONS §6).
    assert request.image == page_request.image
    assert request.instructions == load_photo_check_instructions()
    asked = [rule for rule in enabled_photo_rules(None) if rule.id in ASKED_PHOTO_RULES]
    assert request.prompt == build_photo_check_prompt(asked)


def test_photo_check_prompt_lists_rules_with_id_label_and_description() -> None:
    face, _, _, _, resolution, _ = enabled_photo_rules(None)

    assert build_photo_check_prompt([face, resolution]) == (
        "Değerlendirilecek kurallar (her biri için `rules` listesine bu sırayla bir satır yaz):\n"
        "- `face_visible` — Yüz görünür: Yüz tam ve net görünmeli; kapalı ya da kesik olmamalı.\n"
        "- `min_resolution` — Asgari çözünürlük: Görüntünün piksel boyutu asgari genişlik ve "
        "yüksekliğin altında olmamalı."
    )


def test_photo_check_instructions_forbid_changing_or_describing_the_person() -> None:
    text = load_photo_check_instructions()

    assert "Kırpılmış, düzeltilmiş ya da arka planı değiştirilmiş" in text
    assert "Kişinin kim olduğunu" in text
    assert "`unsure`" in text


# --- 11.7.1: çözünürlük deterministik ölçülür ---------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content", "photo_rules", "result", "note"),
    [
        pytest.param(
            "foto.jpg",
            make_portrait_image_bytes(size=(300, 400)),
            None,
            PhotoRuleResult.FAIL,
            "300×400 piksel; asgari 400×400.",
            id="dusuk-jpeg",
        ),
        pytest.param(
            "foto.png",
            make_portrait_image_bytes("PNG", size=(400, 400)),
            None,
            PhotoRuleResult.PASS,
            "400×400 piksel; asgari 400×400.",
            id="sinirda-png",
        ),
        pytest.param(
            "foto.jpg",
            make_portrait_image_bytes(size=(399, 800)),
            None,
            PhotoRuleResult.FAIL,
            "399×800 piksel; asgari 400×400.",
            id="genislik-eksik",
        ),
        pytest.param(
            "foto.jpg",
            make_half_filled_image_bytes("JPEG", (600, 450), orientation=6),
            {"min_resolution": {"enabled": True, "min_width_px": 500, "min_height_px": 400}},
            PhotoRuleResult.FAIL,
            "450×600 piksel; asgari 500×400.",
            id="exif-yonelimiyle-gorunen-boyut",
        ),
        pytest.param(
            "foto.pdf",
            make_document_pdf_bytes([profile_picture_page(size=(300, 400))]),
            None,
            PhotoRuleResult.FAIL,
            "300×400 piksel; asgari 400×400.",
            id="pdf-gomulu-goruntu",
        ),
        pytest.param(
            "foto.pdf",
            make_text_pdf_bytes(["FOTOGRAF"]),
            None,
            PhotoRuleResult.UNSURE,
            "Sayfa tek bir gömülü görüntü değil; piksel boyutu ölçülemez (asgari 400×400).",
            id="pdf-tek-goruntu-degil",
        ),
    ],
)
def test_resolution_rule_measures_the_photo_s_own_pixels(
    session: Session,
    layout: DataLayout,
    name: str,
    content: bytes,
    photo_rules: dict[str, Any] | None,
    result: PhotoRuleResult,
    note: str,
) -> None:
    # PDF'teki gömülü görüntü sayfa render'ından küçük olsa da ölçülen, çıkarılacak görüntüdür.
    upload = _upload(session, layout, (name, content))
    provider = Scripted(_photo(), photo_check_response())

    (outcome,) = _analyze(session, layout, upload, provider, _catalog(photo_rules)).outcomes

    assert outcome.photo_check is not None
    verdict = outcome.photo_check.verdict("min_resolution")
    assert verdict is not None
    assert (verdict.result, verdict.note) == (result, note)


def test_only_open_rules_are_evaluated_and_resolution_alone_needs_no_provider_call(
    session: Session, layout: DataLayout
) -> None:
    only_resolution = {rule: {"enabled": rule == "min_resolution"} for rule in CATALOG_ORDER}
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    provider = Scripted(_photo())

    (outcome,) = _analyze(session, layout, upload, provider, _catalog(only_resolution)).outcomes

    assert provider.photo_requests == []
    assert outcome.photo_check is not None
    assert [verdict.rule for verdict in outcome.photo_check.rules] == ["min_resolution"]


def test_rule_opened_in_the_catalog_is_asked_and_closed_rule_is_not(
    session: Session, layout: DataLayout
) -> None:
    rules = {"no_head_covering": {"enabled": True}, "single_person": {"enabled": False}}
    asked = ("face_visible", "neutral_expression", "plain_background", "no_sunglasses")
    asked += ("no_head_covering",)
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    provider = Scripted(_photo(), photo_check_response(rules=asked))

    (outcome,) = _analyze(session, layout, upload, provider, _catalog(rules)).outcomes

    (request,) = provider.photo_requests
    assert request.rules == asked
    assert outcome.photo_check is not None
    assert [verdict.rule for verdict in outcome.photo_check.rules] == [
        "face_visible",
        "neutral_expression",
        "plain_background",
        "min_resolution",
        "no_sunglasses",
        "no_head_covering",
    ]


@pytest.mark.parametrize(
    ("analysis", "photo_rules"),
    [
        pytest.param(analysis_payload(), None, id="baska-tur"),
        pytest.param(_photo(is_blank=True, is_readable=False), None, id="bos-sayfa"),
        pytest.param(
            _photo(),
            {rule: {"enabled": False} for rule in CATALOG_ORDER},
            id="butun-kurallar-kapali",
        ),
    ],
)
def test_page_that_is_not_a_photo_with_open_rules_is_not_checked(
    session: Session,
    layout: DataLayout,
    analysis: dict[str, Any],
    photo_rules: dict[str, Any] | None,
) -> None:
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    provider = Scripted(analysis)

    (outcome,) = _analyze(session, layout, upload, provider, _catalog(photo_rules)).outcomes

    assert outcome.status is PageAnalysisStatus.DONE
    assert outcome.photo_check is None
    assert provider.photo_requests == []
    assert _page(upload).photo_check_json is None
    (event,) = _events(session, EventType.PAGE_ANALYZED)
    assert "photo_check" not in event.data_json


# --- kontrol yapılamazsa sayfanın analizi düşer -------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        pytest.param(ProviderConnectionError("ulaşılamadı"), "ProviderConnectionError", id="hata"),
        pytest.param(
            photo_check_response(rules=ASKED_PHOTO_RULES[:-1]), "PhotoCheckError", id="eksik"
        ),
        pytest.param(
            photo_check_response(rules=(*ASKED_PHOTO_RULES, "gozluk_rengi")),
            "PhotoCheckError",
            id="sorulmayan",
        ),
        pytest.param({"rules": [{"rule": "face_visible"}]}, "PhotoCheckError", id="bozuk"),
    ],
)
def test_photo_that_cannot_be_checked_fails_its_page_and_the_batch_continues(
    session: Session, layout: DataLayout, answer: object, error: str
) -> None:
    # Değerlendirilmemiş fotoğraf Hazir'a gidemez: sayfa `failed`, parti `partial` (03.7.2);
    # sonraki dosya analiz edilir.
    upload = _upload(
        session,
        layout,
        ("foto.jpg", make_portrait_image_bytes()),
        ("tarama.jpg", make_half_filled_image_bytes("JPEG")),
    )
    provider = Scripted(_photo(), answer, analysis_payload())

    result = _analyze(session, layout, upload, provider)

    photo, other = result.outcomes
    assert (photo.status, other.status) == (PageAnalysisStatus.FAILED, PageAnalysisStatus.DONE)
    assert photo.analysis is None and photo.photo_check is None
    page = _page(upload)
    assert (page.analysis_json, page.photo_check_json) == (None, None)
    assert upload.status == UploadStatus.PARTIAL
    (event,) = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert (event.file_id, event.page_index) == (upload.files[0].id, 0)
    assert event.data_json == {
        "provider": "scripted",
        "model": "scripted-model",
        "error": error,
        "step": "photo_check",
    }
    # Sorulmayan kuralın kimliği yanıttan gelir; mesaja konmaz.
    assert "gozluk_rengi" not in (event.message or "")
    assert [row.page_index for row in _events(session, EventType.PAGE_ANALYZED)] == [0]


def test_photo_whose_source_cannot_be_measured_fails_its_page(
    session: Session, layout: DataLayout
) -> None:
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    # Yalnız bu test: Inbox kaynağı render'dan sonra kaybolmuş (ölçüm kaynağı okur).
    layout.resolve(upload.files[0].stored_path).unlink()
    provider = Scripted(_photo(), photo_check_response())

    (outcome,) = _analyze(session, layout, upload, provider).outcomes

    assert outcome.status is PageAnalysisStatus.FAILED
    (event,) = _events(session, EventType.PAGE_ANALYSIS_FAILED)
    assert event.data_json["error"] == "PhotoMeasureError"
    assert event.message == "Fotoğrafın piksel boyutu ölçülemedi (FileNotFoundError)."


@pytest.mark.parametrize(
    "second",
    [
        pytest.param([analysis_payload()], id="baska-tur"),
        pytest.param([ProviderConnectionError("yok")], id="analiz-basarisiz"),
    ],
)
def test_reanalysis_that_is_not_a_checked_photo_clears_the_stored_check(
    session: Session, layout: DataLayout, second: list[object]
) -> None:
    # Eski kontrol yeni analizin sonucu gibi okunmasın (plan onu okur).
    upload = _upload(session, layout, ("foto.jpg", make_portrait_image_bytes()))
    _analyze(session, layout, upload, Scripted(_photo(), photo_check_response()))
    assert _page(upload).photo_check_json is not None

    _analyze(session, layout, upload, Scripted(*second))

    assert _page(upload).photo_check_json is None


# --- 11.7.2: kontrol yalnız okur ----------------------------------------------------------------


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_photo_check_changes_no_file_and_leaves_the_photo_as_uploaded(
    session: Session, layout: DataLayout
) -> None:
    # Kırpma, düzeltme, arka plan değişikliği yok: ne Inbox'taki fotoğraf ne analiz kopyası değişir,
    # yeni dosya yazılmaz — hem ihlal eden hem geçen fotoğrafta.
    photos = [
        make_portrait_image_bytes(size=(300, 400), people=2),
        make_document_pdf_bytes([profile_picture_page()]),
    ]
    upload = _upload(session, layout, ("iki-kisi.jpg", photos[0]), ("foto.pdf", photos[1]))
    before = _files(layout.root)
    provider = Scripted(
        _photo(),
        photo_check_response({"single_person": "fail"}),
        _photo(),
        photo_check_response(),
    )

    result = _analyze(session, layout, upload, provider)

    assert [outcome.status for outcome in result.outcomes] == [PageAnalysisStatus.DONE] * 2
    assert _files(layout.root) == before
    for upload_file, content in zip(upload.files, photos, strict=True):
        assert layout.resolve(upload_file.stored_path).read_bytes() == content


# --- ölçüm: `photo_pixel_size` ------------------------------------------------------------------


def test_pixel_size_of_images_and_pdf_pages() -> None:
    assert photo_pixel_size(make_portrait_image_bytes(size=(321, 432)), 0) == (321, 432)
    assert photo_pixel_size(make_portrait_image_bytes("PNG", size=(50, 60)), 0) == (50, 60)
    # Yarım tur (3) boyutu değiştirmez; çeyrek tur (8) genişlikle yüksekliği değiştirir.
    rotated = make_half_filled_image_bytes("JPEG", (200, 100), orientation=3)
    assert photo_pixel_size(rotated, 0) == (200, 100)
    turned = make_half_filled_image_bytes("JPEG", (200, 100), orientation=8)
    assert photo_pixel_size(turned, 0) == (100, 200)
    pdf = make_document_pdf_bytes([profile_picture_page(size=(250, 350))])
    assert photo_pixel_size(pdf, 0) == (250, 350)
    assert photo_pixel_size(make_text_pdf_bytes(["METIN"]), 0) is None


@pytest.mark.parametrize(
    ("content", "page_index", "message"),
    [
        pytest.param(make_portrait_image_bytes(), 1, "tek sayfası", id="goruntunun-ikinci-sayfasi"),
        pytest.param(make_text_pdf_bytes(["A"]), 1, "istenen sayfa yok", id="pdf-sayfa-yok"),
        pytest.param(make_text_pdf_bytes(["A"]), -1, "istenen sayfa yok", id="negatif-sayfa"),
        pytest.param(b"duz metin", 0, "PDF değil", id="desteklenmeyen-icerik"),
    ],
)
def test_pixel_size_refuses_what_it_cannot_measure(
    content: bytes, page_index: int, message: str
) -> None:
    with pytest.raises(RenderError, match=message):
        photo_pixel_size(content, page_index)
