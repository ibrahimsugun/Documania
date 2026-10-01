"""Aday tür incelemesi — PRD 11.5.5 (PLAN.md §C85 "İnceleme").

Sistem bekleyen her aday türün (04.6.1) örnek sayfalarını kendisi inceler ve yapay zekâya tam
katalog kaydı taslağı (`app.ai.type_proposal.TypeProposal`) ürettirir; taslak adayda saklanır ve
onay formunu doldurur (tm 114). Aday kendiliğinden onaylanmaz: onay İK'nın iki aşamalı kararıdır
(K16, 11.5.2).

- **Girdi (`read_examination`).** Adayın her görülmesinin (`sample_page_ids`, her görülmenin ilk
  sayfası) **bütün** sayfaları: ilk sayfası o sayfa olan Unknown kuyruk öğesinin kaynakları (arka
  yüzler, dosyalar arası adayın öteki dosyası dahil; aynı ilk sayfanın birden çok öğesi varsa —
  yeniden analiz, K18 — en yenisi). Öğe bulunamazsa görülme yalnız ilk sayfasıdır. Öğenin durumuna
  bakılmaz: yoksayılan partinin (10.3.4) görülmeleri de örnektir (§D55). Görüntü sayfanın analiz
  kopyasıdır (`pages.image_path`), bellekte okunur, değiştirilmez (K10, K11); görüntüsü kalmamış ya
  da açılamayan sayfa atlanır. İsteğe görülme sırasıyla en çok `MAX_DESCRIPTION_PAGES` görüntü
  girer; hiç görüntü kalmazsa sağlayıcı çağrılmaz, sonuç `no_samples`.
- **Kullanıcı metni (`build_proposal_prompt`).** Aday adı; gözlenen kanıt (`Evidence`: örnek
  dosyaların türü içerikten — 01.2.1, istemcinin bildirdiği `mime`'a güvenilmez —, sayfa
  analizlerindeki `side` değerleri, görülme başına sayfa sayısı); katalog türlerinin ad ve slug
  listesi; varsa hazır önerilen tür kaydı (`SuggestedType`: ad, etiket, ülke — §C86, kaydı tm
  115 getirir); görüntülerin hangi görülmenin hangi sayfası olduğu. Dosya adı ve kişi bilgisi
  isteğe girmez.
- **Kanıt taslağı ezer (`apply_evidence`).** Gözlenen dosya türleri `expected_file_types` olur.
  `front`/`back` gözlendiyse yüz yapısı `front_back` + `separate`, `front_and_back` gözlendiyse
  `combined` (ikisi birlikte olabilir) ve sayfa aralığı düzenlerden türer (`layout_pages`); yalnız
  `single` gözlendiyse `single` ve düzen yok. Kanıt yoksa (`unknown`, analiz yok) yapay zekânın
  değeri kalır. Öteki alanların tutarlılığı onay formunda sınanır (tm 114, `build_entry`).
- **Sızıntı denetimi (`leaks_personal_value`).** Taslağın bütün serbest metinleri (ad, etiket,
  açıklama, kabul kriterleri, görünüm metinleri ve başlıkları) örnek sayfaların `analysis_json`
  kişi değerleriyle karşılaştırılır: soyad, ad, diğer isimler, orijinal yazım (§20.2.1
  normalizasyonuyla kelime kelime — büyük/küçük harf, aksan, Türkçe harf, Kiril/Arap çevirisi fark
  etmez; `MIN_NAME_WORD_LENGTH`'ten kısa kelime sayılmaz), belge ve kişisel numara (harf ve rakam
  dışı karakterler atılarak) ve doğum tarihi (sayısal yazımlar: `YYYY-AA-GG`, `GG.AA.YYYY`,
  `AA/GG/YYYY`, MRZ `YYAAGG` …). Eşleşme varsa taslak saklanmaz, sonuç `failed`, gerekçe
  `LEAK_REASON`; değer hiçbir yere (log, olay, `proposal_json`) yazılmaz (CONVENTIONS §6).
- **Saklama (`store_examination`).** `proposal_status`, `proposal_generated_at` ve `proposal_json`
  (taslak ya da gerekçe, kanıt, model, kullanılan sayfa sayısı) yazılır; adayın açıklaması boşsa
  taslağınki yazılır. Olay `CANDIDATE_TYPE_EXAMINED`: aday kimliği, sonuç, sayfa sayısı, sağlayıcı,
  model (`ai_call_event_data`). Kişisel değer taşımaz.
- **Boş-zaman işi (`CandidateExaminationJob`).** İşçi yükleme kuyruğu boşken (`app.worker.idle`)
  incelenmemiş (`proposal_status IS NULL`) ve karara bağlanmamış (`pending`) adayı koşullu
  sahiplenir; karara bağlanmış aday incelenmez. Sağlayıcı çağrısı açık veritabanı oturumu olmadan
  yapılır. Hata veren inceleme adayı bırakır ve olayını yazar (sonuç `error`, yalnız hata türüyle);
  `WORKER_MAX_ATTEMPTS` deneme tükenince aday `failed` olur ve gerekçesi `ERROR_REASON`'dır.

Aday sayfaları örnek klasörüne kopyalanmaz: çalışan belgesidir (11.2.1).
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.ai.prompts.type_proposal import load_type_proposal_instructions
from app.ai.provider import AnalysisProvider, PageImage, TypeProposalRequest
from app.ai.schemas import Side
from app.ai.type_proposal import TypeProposal
from app.catalog.describe import MAX_DESCRIPTION_PAGES
from app.catalog.schema import FileType, FrontBackLayout, Sides, layout_pages
from app.db.models import (
    CandidateDocumentType,
    CandidateProposalStatus,
    CandidateTypeStatus,
    KnownDocumentType,
    Page,
    QueueItem,
    QueueKind,
    UploadFile,
    utcnow,
)
from app.events import EventType, ai_call_event_data, record_event
from app.matching.names import EmptyNameError, normalize_name
from app.storage import DataLayout, detect_file_kind
from app.worker.idle import IdleContext, IdleTable, run_idle_unit

JOB_NAME = "aday-tur-incelemesi"

LEAK_REASON = "Taslakta örnekteki kişiye ait değer bulundu"
"""Sızıntı denetiminden geçmeyen taslağın gerekçesi; değerin kendisi yazılmaz."""

NO_SAMPLES_REASON = "Görüntüsü kalan örnek sayfa yok"
ERROR_REASON = "Tür taslağı üretilemedi"
"""Denemeleri tükenen incelemenin gerekçesi (sağlayıcı hatası ya da şemaya uymayan yanıt)."""

MIN_NAME_WORD_LENGTH = 3
"""Sızıntı denetiminde sayılan en kısa isim kelimesi: daha kısası (baş harf, `Li`, `Ay`) Türkçe
metnin sıradan kelimeleriyle (`ve`, `ad`, `ön`) karışır."""

MIN_NUMBER_LENGTH = 4
"""Sızıntı denetiminde sayılan en kısa numara (harf ve rakam)."""

_HEAD_BYTES = 4096
_NAME_FIELDS = ("surname", "given_names", "other_names", "original_script_name")
_NUMBER_FIELDS = ("document_number", "personal_number")
_DATE_SEPARATED = re.compile(r"[0-9]+(?:[ ./-][0-9]+)*")
_DATE_PARTS = re.compile(r"[ ./-]")


# --- girdi -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SamplePage:
    """Bir görülmenin sayfası: dosyası, 0 tabanlı sırası ve analiz görüntüsünün saklı yolu."""

    file_id: int
    index: int
    image_path: str | None


@dataclass(frozen=True, slots=True)
class PersonalValues:
    """Örnek sayfalardaki kişi değerlerinin karşılaştırma biçimleri (sızıntı denetimi). Yalnız
    bellekte durur; hiçbir yere yazılmaz."""

    name_words: frozenset[str] = frozenset()
    numbers: frozenset[str] = frozenset()
    dates: frozenset[date] = frozenset()


@dataclass(frozen=True, slots=True)
class SuggestedType:
    """Hazır önerilen tür kaydının adayla eşleşen satırı (§C86): ad, etiket, ülke."""

    name: str
    file_label: str
    country: str | None


@dataclass(frozen=True, slots=True)
class ExaminationSource:
    """İncelemenin veritabanından okunan girdisi (oturumdan bağımsız).

    `sightings` görülme sırasıyla her görülmenin sayfaları; `stored_paths` görülmelerin
    dosyalarının saklı yolları (dosya türü içerikten okunur); `sides` sayfa analizlerinde gözlenen
    yüzler; `catalog` katalog türlerinin `(ad, slug)` listesi.
    """

    candidate_id: int
    name: str
    sightings: tuple[tuple[SamplePage, ...], ...]
    stored_paths: Mapping[int, str]
    sides: frozenset[Side]
    personal: PersonalValues
    catalog: tuple[tuple[str, str], ...]
    suggested: SuggestedType | None = None


def read_examination(
    session: Session, candidate: CandidateDocumentType, *, suggested: SuggestedType | None = None
) -> ExaminationSource:
    """Adayın inceleme girdisini okur (modül açıklaması, "Girdi"); yalnız okur."""
    firsts = _first_pages(session, candidate.sample_page_ids)
    items = _unknown_item_sources(session, set(firsts))
    refs = [items.get(first, ((first[0], (first[1],)),)) for first in firsts]
    file_ids = {file_id for sighting in refs for file_id, _ in sighting}
    pages: dict[tuple[int, int], Page] = {}
    if file_ids:
        for page in session.scalars(select(Page).where(Page.file_id.in_(file_ids))):
            pages[page.file_id, page.index] = page
    sightings: list[tuple[SamplePage, ...]] = []
    analyses: list[Mapping[str, Any]] = []
    for sighting in refs:
        taken: list[SamplePage] = []
        for file_id, indexes in sighting:
            # Boş sayfa listesi dosyanın bütünüdür (K15).
            wanted = indexes or tuple(sorted(i for f, i in pages if f == file_id))
            for index in wanted:
                page = pages.get((file_id, index))
                if page is None:
                    continue
                taken.append(SamplePage(file_id, index, page.image_path))
                if isinstance(page.analysis_json, Mapping):
                    analyses.append(page.analysis_json)
        sightings.append(tuple(taken))
    stored_paths = {
        file_id: stored_path
        for file_id, stored_path in session.execute(
            select(UploadFile.id, UploadFile.stored_path).where(UploadFile.id.in_(file_ids))
        )
    }
    catalog = tuple(
        (name, slug)
        for name, slug in session.execute(
            select(KnownDocumentType.name, KnownDocumentType.slug).order_by(KnownDocumentType.slug)
        )
    )
    return ExaminationSource(
        candidate_id=candidate.id,
        name=candidate.proposed_name,
        sightings=tuple(sightings),
        stored_paths=stored_paths,
        sides=_observed_sides(analyses),
        personal=personal_values(analyses),
        catalog=catalog,
        suggested=suggested,
    )


def _first_pages(session: Session, page_ids: Sequence[int]) -> list[tuple[int, int]]:
    """Örnek sayfaların `(dosya, sıra)` karşılıkları, görülme sırasıyla; bulunmayan düşer."""
    if not page_ids:
        return []
    rows = session.execute(
        select(Page.id, Page.file_id, Page.index).where(Page.id.in_(page_ids))
    ).all()
    found = {page_id: (file_id, index) for page_id, file_id, index in rows}
    return [found[page_id] for page_id in dict.fromkeys(page_ids) if page_id in found]


def _unknown_item_sources(
    session: Session, firsts: set[tuple[int, int]]
) -> dict[tuple[int, int], tuple[tuple[int, tuple[int, ...]], ...]]:
    """İlk sayfası `firsts`'ten biri olan Unknown öğelerinin kaynakları; aynı ilk sayfada en yeni
    öğe (kimliği en büyük) kazanır. Kaydı bozuk öğe atlanır."""
    if not firsts:
        return {}
    found: dict[tuple[int, int], tuple[tuple[int, tuple[int, ...]], ...]] = {}
    items = session.scalars(
        select(QueueItem.payload_json)
        .where(QueueItem.kind == QueueKind.UNKNOWN.value)
        .order_by(QueueItem.id)
    )
    for payload in items:
        sources = _sources(payload)
        if not sources or not sources[0][1]:
            continue
        first = (sources[0][0], sources[0][1][0])
        if first in firsts:
            found[first] = sources
    return found


def _sources(payload: object) -> tuple[tuple[int, tuple[int, ...]], ...] | None:
    """Kuyruk kaydının `sources` listesi `(dosya, sayfalar)` olarak; biçim bozuksa `None`."""
    raw = payload.get("sources") if isinstance(payload, Mapping) else None
    if not isinstance(raw, list) or not raw:
        return None
    sources = []
    for ref in raw:
        if not isinstance(ref, Mapping):
            return None
        file_id, pages = ref.get("file_id"), ref.get("pages", [])
        if type(file_id) is not int or not isinstance(pages, list):
            return None
        if any(type(page) is not int for page in pages):
            return None
        sources.append((file_id, tuple(pages)))
    return tuple(sources)


def _observed_sides(analyses: Iterable[Mapping[str, Any]]) -> frozenset[Side]:
    sides = set()
    for analysis in analyses:
        try:
            sides.add(Side(analysis.get("side")))
        except ValueError:
            continue
    return frozenset(sides)


# --- kişi değerleri ve sızıntı denetimi ------------------------------------------------------


def personal_values(analyses: Iterable[Mapping[str, Any]]) -> PersonalValues:
    """Sayfa analizlerinin (`pages.analysis_json`) kişi değerleri: `person` ve aynı adlı alan
    okumaları (`fields`). Saklanan kayıt şemaya uymasa da okunabilen her değer alınır — denetim
    kayıt bozuk diye atlanmaz."""
    words: set[str] = set()
    numbers: set[str] = set()
    dates: set[date] = set()
    for analysis in analyses:
        language = analysis.get("language")
        language = language if isinstance(language, str) else None
        for name in _NAME_FIELDS:
            for value in _read_values(analysis, name):
                words.update(_name_words(value, language))
        for name in _NUMBER_FIELDS:
            for value in _read_values(analysis, name):
                compact = _compact(value)
                if len(compact) >= MIN_NUMBER_LENGTH:
                    numbers.add(compact)
        for value in _read_values(analysis, "date_of_birth"):
            parsed = _iso_date(value)
            if parsed is not None:
                dates.add(parsed)
            else:
                # Belgedeki yazımıyla okunmuş tarih (`12.04.1990`): rakamları numara gibi aranır.
                compact = _compact(value)
                if len(compact) >= MIN_NUMBER_LENGTH:
                    numbers.add(compact)
    return PersonalValues(frozenset(words), frozenset(numbers), frozenset(dates))


def _read_values(analysis: Mapping[str, Any], name: str) -> list[str]:
    """Kişi alanının (`person.<ad>`) ve aynı adlı alan okumasının (`fields.<ad>.value`) dolu
    metinleri."""
    person = analysis.get("person")
    fields = analysis.get("fields")
    found = [person.get(name) if isinstance(person, Mapping) else None]
    reading = fields.get(name) if isinstance(fields, Mapping) else None
    if isinstance(reading, Mapping):
        found.append(reading.get("value"))
    return [value for value in found if isinstance(value, str) and value.strip()]


def proposal_texts(proposal: TypeProposal) -> list[str]:
    """Taslağın serbest metinleri: ad, etiket, açıklama, kabul kriterleri ve görünüm metinleri."""
    appearance = proposal.appearance
    texts = [
        proposal.name,
        proposal.file_label,
        proposal.description,
        *proposal.acceptance_criteria,
        appearance.layout,
        *appearance.headings,
        *(item.location for item in appearance.field_locations),
    ]
    if appearance.mrz is not None:
        texts.append(appearance.mrz.location)
    optional = (appearance.side_differences, appearance.accepted_photo)
    return texts + [text for text in optional if text is not None]


def leaks_personal_value(texts: Iterable[str], personal: PersonalValues) -> bool:
    """Metinlerden biri örnekteki kişiye ait bir değer taşıyor mu? Değer döndürülmez."""
    date_forms = {form for value in personal.dates for form in _date_forms(value)}
    for text in texts:
        if personal.name_words and personal.name_words & _name_words(text, None):
            return True
        if personal.numbers:
            compact = _compact(text)
            if any(number in compact for number in personal.numbers):
                return True
        if date_forms:
            runs = _digit_runs(text)
            if any(form in run for run in runs for form in date_forms):
                return True
    return False


def _name_words(text: str, language: str | None) -> set[str]:
    """§20.2.1 normalizasyonunun kelimeleri; belgenin diliyle ve dilsiz çeviri birlikte (Kiril
    dil istisnaları taslağın yazımını değiştirebilir)."""
    words: set[str] = set()
    for lang in dict.fromkeys((language, None)):
        try:
            words.update(normalize_name(text, language=lang).split())
        except EmptyNameError:
            continue
    return {word for word in words if len(word) >= MIN_NAME_WORD_LENGTH}


def _compact(text: str) -> str:
    """Harf büyüklüğü ve aksan katlanmış, yalnız harf ve rakam."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in folded if char.isalnum())


def _iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _date_forms(value: date) -> set[str]:
    year, month, day = f"{value.year:04d}", f"{value.month:02d}", f"{value.day:02d}"
    short = year[2:]
    return {
        year + month + day,
        day + month + year,
        month + day + year,
        short + month + day,  # MRZ
        day + month + short,
    }


def _digit_runs(text: str) -> list[str]:
    """Metindeki ayraçlı ya da ayraçsız rakam dizileri, tek haneli parçalar sıfırla doldurulmuş
    (`12.4.1990` → `12041990`)."""
    runs = []
    for match in _DATE_SEPARATED.finditer(text):
        parts = _DATE_PARTS.split(match.group())
        runs.append("".join(part.zfill(2) for part in parts))
    return runs


# --- inceleme --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Evidence:
    """Örneklerden gözlenen kanıt: dosya türleri (`FileType` sırasıyla), sayfa yüzleri (`Side`
    sırasıyla) ve görülme başına sayfa sayısı (görülme sırasıyla)."""

    file_types: tuple[FileType, ...]
    sides: tuple[Side, ...]
    pages_per_sighting: tuple[int, ...]

    def to_json(self) -> dict[str, list[Any]]:
        return {
            "file_types": [value.value for value in self.file_types],
            "sides": [value.value for value in self.sides],
            "pages_per_sighting": list(self.pages_per_sighting),
        }


@dataclass(frozen=True, slots=True)
class ImageLabel:
    """İsteğe giren görüntünün yeri: 1 tabanlı görülme ve görülme içindeki sayfa numarası."""

    sighting: int
    page: int


@dataclass(frozen=True, slots=True)
class Examination:
    """İncelemenin sonucu. `proposal` yalnız `ready`'de doludur; `reason` başarısızlık ya da
    örneksizlik gerekçesidir (kişisel değer taşımaz); `pages` isteğe giren görüntü sayısıdır."""

    status: CandidateProposalStatus
    evidence: Evidence
    pages: int
    proposal: TypeProposal | None = None
    reason: str | None = None


def observe(source: ExaminationSource, layout: DataLayout) -> Evidence:
    """Girdiden gözlenen kanıt; dosya türü dosyanın ilk baytlarından okunur (01.2.1)."""
    kinds = set()
    for stored_path in source.stored_paths.values():
        kind = _file_type(layout, stored_path)
        if kind is not None:
            kinds.add(kind)
    return Evidence(
        file_types=tuple(value for value in FileType if value in kinds),
        sides=tuple(value for value in Side if value in source.sides),
        pages_per_sighting=tuple(len(sighting) for sighting in source.sightings),
    )


def _file_type(layout: DataLayout, stored_path: str) -> FileType | None:
    try:
        with layout.resolve(stored_path).open("rb") as handle:
            head = handle.read(_HEAD_BYTES)
        return FileType(detect_file_kind(head).value)
    except (ValueError, OSError):
        # Geçersiz saklı yol, tanınmayan içerik (`UnsupportedFileTypeError`) ya da dosya yok.
        return None


def collect_sample_images(
    source: ExaminationSource, layout: DataLayout, *, max_pages: int = MAX_DESCRIPTION_PAGES
) -> tuple[tuple[PageImage, ...], tuple[ImageLabel, ...]]:
    """Görülme sırasıyla en çok `max_pages` sayfanın analiz görüntüsü (bellekte) ve yerleri.
    Görüntüsü kalmamış ya da açılamayan sayfa atlanır; aynı sayfa bir kez girer."""
    images: list[PageImage] = []
    labels: list[ImageLabel] = []
    seen: set[tuple[int, int]] = set()
    for number, sighting in enumerate(source.sightings, start=1):
        for position, page in enumerate(sighting, start=1):
            if len(images) >= max_pages:
                return tuple(images), tuple(labels)
            key = (page.file_id, page.index)
            if key in seen or page.image_path is None:
                continue
            seen.add(key)
            image = _page_image(layout, page.image_path)
            if image is None:
                continue
            images.append(image)
            labels.append(ImageLabel(number, position))
    return tuple(images), tuple(labels)


def _page_image(layout: DataLayout, image_path: str) -> PageImage | None:
    try:
        return PageImage(layout.resolve(image_path).read_bytes())
    except (ValueError, OSError):
        # Önbellekten silinmiş (`OSError`), geçersiz yol ya da JPEG/PNG olmayan içerik.
        return None


def build_proposal_prompt(
    name: str,
    evidence: Evidence,
    catalog: Sequence[tuple[str, str]],
    labels: Sequence[ImageLabel],
    *,
    suggested: SuggestedType | None = None,
) -> str:
    """İsteğin kullanıcı metni (modül açıklaması, "Kullanıcı metni")."""
    lines = [
        f"Geçici ad: {name}",
        "",
        "Gözlenen kanıt:",
        f"- Örnek dosya türleri: {_listed(evidence.file_types)}",
        f"- Sayfa yüzleri (sayfa analizinden): {_listed(evidence.sides)}",
        f"- Görülme sayısı: {len(evidence.pages_per_sighting)}",
        "- Görülme başına sayfa sayısı: "
        + (", ".join(str(count) for count in evidence.pages_per_sighting) or "belirlenemedi"),
        "",
        "Katalogdaki türler:",
        *([f"- {type_name} (`{slug}`)" for type_name, slug in catalog] or ["- yok"]),
    ]
    if suggested is not None:
        lines += [
            "",
            "Hazır önerilen tür kaydı:",
            f"- Ad: {suggested.name}",
            f"- Etiket: {suggested.file_label}",
            f"- Ülke: {suggested.country or 'belirtilmemiş'}",
        ]
    lines += [
        "",
        f"Görüntüler ({len(labels)}, gönderildiği sırayla):",
        *(
            f"{number}. görülme {label.sighting}, sayfa {label.page}"
            for number, label in enumerate(labels, start=1)
        ),
    ]
    return "\n".join(lines)


def _listed(values: Sequence[FileType] | Sequence[Side]) -> str:
    return ", ".join(value.value for value in values) or "belirlenemedi"


def apply_evidence(proposal: TypeProposal, evidence: Evidence) -> TypeProposal:
    """Gözlenen kanıt taslağın dosya türlerini ve yüz yapısını ezer (modül açıklaması)."""
    update: dict[str, Any] = {}
    if evidence.file_types:
        update["expected_file_types"] = evidence.file_types
    observed = set(evidence.sides)
    layouts = []
    if observed & {Side.FRONT, Side.BACK}:
        layouts.append(FrontBackLayout.SEPARATE)
    if Side.FRONT_AND_BACK in observed:
        layouts.append(FrontBackLayout.COMBINED)
    if layouts:
        update |= {
            "sides": Sides.FRONT_BACK,
            "front_back_layouts": tuple(layouts),
            "expected_pages": layout_pages(tuple(layouts)),
        }
    elif Side.SINGLE in observed:
        update |= {"sides": Sides.SINGLE, "front_back_layouts": ()}
    if not update:
        return proposal
    return TypeProposal.model_validate(proposal.model_dump() | update)


def examine(
    source: ExaminationSource,
    layout: DataLayout,
    provider: AnalysisProvider,
    *,
    max_pages: int = MAX_DESCRIPTION_PAGES,
) -> Examination:
    """Adayı inceler (modül açıklaması); hiçbir şey kaydetmez ve veritabanına dokunmaz.

    Sağlayıcı hataları (`ProviderError`) ve şemaya uymayan yanıt (`TypeProposalError`) olduğu gibi
    yükselir.
    """
    evidence = observe(source, layout)
    images, labels = collect_sample_images(source, layout, max_pages=max_pages)
    if not images:
        return Examination(
            CandidateProposalStatus.NO_SAMPLES, evidence, pages=0, reason=NO_SAMPLES_REASON
        )
    request = TypeProposalRequest(
        images=images,
        instructions=load_type_proposal_instructions(),
        prompt=build_proposal_prompt(
            source.name, evidence, source.catalog, labels, suggested=source.suggested
        ),
    )
    proposal = apply_evidence(provider.propose_type(request), evidence)
    if leaks_personal_value(proposal_texts(proposal), source.personal):
        return Examination(
            CandidateProposalStatus.FAILED, evidence, pages=len(images), reason=LEAK_REASON
        )
    return Examination(
        CandidateProposalStatus.READY, evidence, pages=len(images), proposal=proposal
    )


# --- saklama ---------------------------------------------------------------------------------


def store_examination(
    session: Session,
    candidate: CandidateDocumentType,
    examination: Examination,
    *,
    provider: AnalysisProvider,
) -> None:
    """Sonucu adaya yazar ve `CANDIDATE_TYPE_EXAMINED`'ı kaydeder; commit etmez. Adayın açıklaması
    boşsa taslağınki yazılır."""
    proposal = examination.proposal
    candidate.proposal_status = examination.status.value
    candidate.proposal_generated_at = utcnow()
    candidate.proposal_json = {
        "proposal": None if proposal is None else proposal.model_dump(mode="json"),
        "reason": examination.reason,
        "evidence": examination.evidence.to_json(),
        "model": provider.model,
        "pages": examination.pages,
    }
    if proposal is not None and not (candidate.description or "").strip():
        candidate.description = proposal.description
    _record(
        session,
        candidate,
        result=examination.status.value,
        pages=examination.pages,
        provider=provider,
    )


def store_error(
    session: Session,
    candidate: CandidateDocumentType,
    *,
    error: str,
    final: bool,
    provider: AnalysisProvider,
) -> None:
    """Hata veren incelemenin olayını yazar; `final` ise (denemeler tükendi) gerekçeyi de. Durum
    (`failed`) boş-zaman çerçevesinin işidir. `error` hatanın türüdür, mesajı değil."""
    if final:
        candidate.proposal_generated_at = utcnow()
        candidate.proposal_json = {
            "proposal": None,
            "reason": ERROR_REASON,
            "evidence": None,
            "model": provider.model,
            "pages": None,
        }
    _record(
        session,
        candidate,
        result=CandidateProposalStatus.FAILED.value if final else "error",
        pages=None,
        provider=provider,
        error=error,
    )


def _record(
    session: Session,
    candidate: CandidateDocumentType,
    *,
    result: str,
    pages: int | None,
    provider: AnalysisProvider,
    error: str | None = None,
) -> None:
    data: dict[str, object] = {"candidate_type_id": candidate.id, "result": result}
    if pages is not None:
        data["pages"] = pages
    if error is not None:
        data["error"] = error
    data |= ai_call_event_data(provider=provider.name, model=provider.model)
    record_event(session, EventType.CANDIDATE_TYPE_EXAMINED, data=data)


def load_proposal(candidate: CandidateDocumentType) -> TypeProposal | None:
    """Adayda saklanan tür taslağı; inceleme `ready` değilse ya da kayıt okunamıyorsa `None`."""
    if candidate.proposal_status != CandidateProposalStatus.READY.value:
        return None
    stored = candidate.proposal_json
    raw = stored.get("proposal") if isinstance(stored, Mapping) else None
    try:
        return TypeProposal.model_validate(raw)
    except ValidationError:
        return None


# --- boş-zaman işi ---------------------------------------------------------------------------

CANDIDATE_EXAMINATIONS = IdleTable(
    CandidateDocumentType,
    pending=lambda: and_(
        CandidateDocumentType.proposal_status.is_(None),
        CandidateDocumentType.status == CandidateTypeStatus.PENDING.value,
    ),
    failed={"proposal_status": CandidateProposalStatus.FAILED.value},
)
"""İncelenmemiş, karara bağlanmamış adaylar; deneme tükenince `failed`."""


class CandidateExaminationJob:
    """İşçinin boş-zaman işi: sıradaki incelenmemiş bekleyen adayı inceler (`IdleJob`)."""

    name = JOB_NAME

    def __init__(self, *, max_pages: int = MAX_DESCRIPTION_PAGES) -> None:
        self._max_pages = max_pages

    def run_one(self, context: IdleContext) -> bool:
        provider = context.provider

        def call(provider: AnalysisProvider, source: ExaminationSource) -> Examination:
            return examine(source, context.layout, provider, max_pages=self._max_pages)

        def write(
            session: Session,
            candidate: CandidateDocumentType,
            examination: Examination,
        ) -> None:
            store_examination(session, candidate, examination, provider=provider)

        def failed(session: Session, candidate: CandidateDocumentType, final: bool) -> None:
            # Çerçeve bu kancayı hatanın `except` bloğunda çağırır; yalnız türü yazılır.
            active = sys.exception()
            error = type(active).__name__ if active is not None else "Exception"
            store_error(session, candidate, error=error, final=final, provider=provider)

        return run_idle_unit(
            context,
            CANDIDATE_EXAMINATIONS,
            name=self.name,
            read=read_examination,
            call=call,
            write=write,
            failed=failed,
        )
