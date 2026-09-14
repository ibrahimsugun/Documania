"""Dosya içi gruplama ve ön/arka yüz eşleşmesi — PRD 04.1.1, 04.1.2.

Bir dosyanın analiz edilmiş sayfaları `pages.index` sırasıyla **belge adaylarına** ayrılır (§4:
karar motorunun aynı belgeye ait olduğuna hükmettiği sayfa grubu). Sayfa açık adaya ancak aşağıdaki
koşulların hepsi sağlanırsa katılır; biri bile sağlanmazsa yeni aday başlatır:

1. **Ardışık:** adayın son sayfası, bu sayfadan hemen önce analize gönderilen sayfadır. Boş sayfa
   (02.4.1) analize gönderilmez ve başka belgeye ait sayfa değildir: zinciri kırmaz, adaya da girmez
   (S8 "atlanır"; dupleks taramada kartın iki yüzü arasına girer). Analizi başarısız ya da hiç
   yapılmamış sayfanın içeriği bilinmez — başka bir belge olabilir (K5) — zinciri kırar. Analizcinin
   boş dediği ve hiçbir şey okumadığı sayfa da zinciri kırar: sonraki sayfanın devam işareti o boş
   sayfaya göre verilmiştir. Bu sayfalar aday olmaz.
2. **Devam:** sayfanın `continues_previous_page` değeri `true`. Aynı kişinin art arda taranmış iki
   aynı tür belgesini (ör. eski ve yeni pasaport) ayıran işaret budur; `false` bölmek demektir
   (C14).
3. **Aynı tür:** aynı katalog slug'ı; katalog dışı sayfada aynı aday tür adı (harf büyüklüğü ve
   boşluk farkı yok sayılır). Türü belirlenemeyen sayfa hiçbir sayfayla gruplanmaz.
4. **Yüz yapısı (04.1.2):** katalogda `sides: front_back` olan türde ön yüz ve onu izleyen arka yüz
   sırayla eşleşir — aday yalnız ön yüzden oluşuyorsa ve sayfa arka yüzse katılır. Tamamlanmış çift
   başka sayfa almaz; arka yüzden sonra gelen ön yüz ve `single`/`unknown` yüzlü sayfa eşleşmez.
   Tek yüzlü ve katalog dışı türde yüz sınır değildir. Sayfa sayısı sınırı gruplamada uygulanmaz:
   sınırda bölmek geçerli görünen yanlış belgeler üretirdi; aralık dışı aday 04.5'te Unresolved
   olur. Katalogda bulunmayan slug'ın yüz yapısı bilinmediği için gruplanmaz.
5. **Aynı kişi:** iki sayfada da yazılı hiçbir kimlik değeri çelişmez — belge numarası (§20.2.1
   normalizasyonu), doğum tarihi, soyad, ad ve orijinal yazım. İsimlerde harf büyüklüğü, aksan,
   noktalama ve kelime sırası farkı yok sayılır; kelime kümelerinden biri ötekini kapsamıyorsa
   çelişkidir (ikinci adı yazılmamış sayfa çelişmez). Değeri olmayan sayfa (ör. kartın arka yüzü)
   çelişmez. Katılacak sayfa adayın her sayfasıyla karşılaştırılır.

Aday eksik olabilir (yalnız ön ya da yalnız arka yüz, beklenen sayfa sayısı dışında); bu modül rota
seçmez: araya başka belge girmesi 04.2'nin, başka dosyadaki eş 04.3'ün, sayfa sayısı 04.5'in işidir.

`group_upload` partinin tekrar olmayan dosyalarını ayrı ayrı gruplar ve her aday için bir olay
yazar: katalog türünde `DOC_TYPE_DETERMINED`, değilse `DOC_TYPE_UNKNOWN` (veri: slug veya aday tür
adı, sayfalar, yüzler — kişisel değer yok). Oturum commit edilmez; işlem sınırı çağıranındır.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis, PagePerson, Side
from app.catalog import Catalog, Sides
from app.db.models import Page, Upload, UploadFile
from app.events import EventType, event_context, record_event
from app.pipeline.analyze import PageAnalysisStatus

# §20.2.1: belge numarası büyük harfe çevrilir; boşluk, tire, nokta ve eğik çizgi silinir.
_NUMBER_SEPARATORS = re.compile(r"[\s./-]+")
_NON_WORD = re.compile(r"[\W_]+")
_NAME_FIELDS = ("surname", "given_names", "original_script_name")


class StoredAnalysisError(ValueError):
    """Saklanan `pages.analysis_json` §8.4 şemasına uymuyor; mesaj gelen değeri tekrarlamaz."""


@dataclass(frozen=True, slots=True)
class GroupingPage:
    """Gruplamanın okuduğu sayfa; `analysis` yalnız analizi tamamlanmış sayfada doludur."""

    index: int
    is_blank: bool = False
    analysis: PageAnalysis | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CandidatePage:
    """Belge adayındaki tek sayfa: kaynak dosyası, dosyadaki sırası ve analizi."""

    file_id: int
    index: int
    analysis: PageAnalysis = field(repr=False)


@dataclass(frozen=True, slots=True)
class DocumentCandidate:
    """Aynı belgeye ait olduğuna hükmedilen sayfalar, kaynaktaki sırasıyla."""

    pages: tuple[CandidatePage, ...]

    @property
    def document_type_slug(self) -> str | None:
        return self.pages[0].analysis.document_type_slug

    @property
    def candidate_type_name(self) -> str | None:
        """Katalog dışı adayın tür adı, ilk sayfada yazıldığı gibi."""
        return self.pages[0].analysis.candidate_type_name

    @property
    def sides(self) -> tuple[Side, ...]:
        return tuple(page.analysis.side for page in self.pages)


@dataclass(frozen=True, slots=True)
class FileGrouping:
    """Tek dosyanın gruplaması; boş ve analizsiz sayfalar hiçbir adaya girmez."""

    file_id: int
    candidates: tuple[DocumentCandidate, ...]
    blank_pages: tuple[int, ...] = ()
    unanalyzed_pages: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class UploadGrouping:
    """Partinin tekrar olmayan dosyalarının gruplaması, dosya sırasıyla."""

    files: tuple[FileGrouping, ...]

    @property
    def candidates(self) -> tuple[DocumentCandidate, ...]:
        return tuple(candidate for grouping in self.files for candidate in grouping.candidates)


def group_upload(session: Session, upload: Upload, *, catalog: Catalog) -> UploadGrouping:
    """Partinin her dosyasını ayrı gruplar (04.1) ve her adayı olay loguna yazar.

    Tekrar dosyası (01.4.1) gruplanmaz: analiz edilmemiştir ve çıktı üretmez. `catalog`, türlerin
    yüz yapısının okunduğu güncel katalogdur (`export_catalog(session)`).
    """
    groupings: list[FileGrouping] = []
    for upload_file in upload.files:
        if upload_file.is_duplicate_of is not None:
            continue
        grouping = group_file_pages(upload_file.id, _grouping_pages(upload_file), catalog=catalog)
        with event_context(upload_id=upload_file.upload_id, file_id=upload_file.id):
            for candidate in grouping.candidates:
                _record_candidate(session, candidate)
        groupings.append(grouping)
    return UploadGrouping(tuple(groupings))


def group_file_pages(
    file_id: int, pages: Iterable[GroupingPage], *, catalog: Catalog
) -> FileGrouping:
    """Tek dosyanın sayfalarını belge adaylarına ayırır; kurallar modül açıklamasındadır."""
    ordered = sorted(pages, key=lambda page: page.index)
    if len({page.index for page in ordered}) != len(ordered):
        raise ValueError("Aynı dosyada bir sayfa sırası birden fazla kez verildi")
    candidates: list[DocumentCandidate] = []
    blank: list[int] = []
    unanalyzed: list[int] = []
    current: list[CandidatePage] = []
    for page in ordered:
        if page.is_blank:
            blank.append(page.index)
            continue
        analysis = page.analysis
        if analysis is not None and current and _joins(current, analysis, catalog):
            current.append(CandidatePage(file_id, page.index, analysis))
            continue
        if current:
            candidates.append(DocumentCandidate(tuple(current)))
            current = []
        if analysis is None:
            unanalyzed.append(page.index)
        elif _reads_as_blank(analysis):
            blank.append(page.index)
        else:
            current = [CandidatePage(file_id, page.index, analysis)]
    if current:
        candidates.append(DocumentCandidate(tuple(current)))
    return FileGrouping(file_id, tuple(candidates), tuple(blank), tuple(unanalyzed))


def _joins(candidate: Sequence[CandidatePage], analysis: PageAnalysis, catalog: Catalog) -> bool:
    key = _type_key(analysis)
    return (
        analysis.continues_previous_page
        and key is not None
        and key == _type_key(candidate[0].analysis)
        and _faces_match(candidate, analysis, catalog)
        and not any(_identity_conflict(page.analysis.person, analysis.person) for page in candidate)
    )


def _type_key(analysis: PageAnalysis) -> tuple[str, str] | None:
    if analysis.document_type_slug is not None:
        return ("slug", analysis.document_type_slug)
    if analysis.candidate_type_name is not None:
        return ("candidate", " ".join(analysis.candidate_type_name.casefold().split()))
    return None


def _faces_match(
    candidate: Sequence[CandidatePage], analysis: PageAnalysis, catalog: Catalog
) -> bool:
    slug = analysis.document_type_slug
    if slug is None:
        return True
    entry = catalog.get(slug)
    if entry is None:
        return False
    if entry.sides == Sides.FRONT_BACK:
        faces = [page.analysis.side for page in candidate]
        return faces == [Side.FRONT] and analysis.side == Side.BACK
    return True


def _identity_conflict(first: PagePerson, second: PagePerson) -> bool:
    numbers = (
        _document_number_key(first.document_number),
        _document_number_key(second.document_number),
    )
    if all(numbers) and numbers[0] != numbers[1]:
        return True
    births = first.date_of_birth, second.date_of_birth
    if None not in births and births[0] != births[1]:
        return True
    for name in _NAME_FIELDS:
        words = _name_words(getattr(first, name)), _name_words(getattr(second, name))
        if all(words) and not (words[0] <= words[1] or words[1] <= words[0]):
            return True
    return False


def _document_number_key(value: str | None) -> str:
    return "" if value is None else _NUMBER_SEPARATORS.sub("", value.upper())


def _name_words(value: str | None) -> frozenset[str]:
    if value is None:
        return frozenset()
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    letters = "".join(char for char in decomposed if not unicodedata.combining(char))
    # Noktasız `ı`nın ayrışmış biçimi yok; `I`nın küçük harfiyle (`i`) aynı anahtara iner.
    return frozenset(_NON_WORD.sub(" ", letters.replace("ı", "i")).split())


def _reads_as_blank(analysis: PageAnalysis) -> bool:
    # Çelişkili yanıt (boş denmiş ama tür, kişi değeri veya okunaklı alan var) boş sayılmaz.
    person = analysis.person.model_dump()
    contact = person.pop("contact")
    return (
        analysis.is_blank
        and _type_key(analysis) is None
        and all(value is None for value in (*person.values(), *contact.values()))
        and not any(reading.legible for reading in analysis.fields.values())
    )


def _grouping_pages(upload_file: UploadFile) -> list[GroupingPage]:
    return [
        GroupingPage(index=page.index, is_blank=page.is_blank, analysis=_stored_analysis(page))
        for page in upload_file.pages
    ]


def _stored_analysis(page: Page) -> PageAnalysis | None:
    if page.analysis_status != PageAnalysisStatus.DONE or page.analysis_json is None:
        return None
    try:
        # Saklanan analiz katalogsuz okunur (C12): katalog analizden sonra değişmiş olabilir.
        return PageAnalysis.model_validate(page.analysis_json)
    except ValidationError as exc:
        # Gelen değer mesaja konmaz (CONVENTIONS §6); yalnız alan konumu ve kural.
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'yanıt'}: {error['msg']}"
            for error in exc.errors(include_url=False, include_input=False, include_context=False)
        )
        raise StoredAnalysisError(
            f"Saklanan sayfa analizi §8.4 şemasına uymuyor (dosya {page.file_id}, "
            f"sayfa {page.index}): {problems}"
        ) from None


def _record_candidate(session: Session, candidate: DocumentCandidate) -> None:
    # Olay verisi kişisel değer taşımaz (CONVENTIONS §6); değerler `pages.analysis_json`'dadır.
    data: dict[str, object] = {
        "pages": [page.index for page in candidate.pages],
        "sides": [side.value for side in candidate.sides],
    }
    if candidate.document_type_slug is not None:
        event_type = EventType.DOC_TYPE_DETERMINED
        data = {"document_type_slug": candidate.document_type_slug, **data}
    else:
        event_type = EventType.DOC_TYPE_UNKNOWN
        data = {"candidate_type_name": candidate.candidate_type_name, **data}
    record_event(session, event_type, page_index=candidate.pages[0].index, data=data)
