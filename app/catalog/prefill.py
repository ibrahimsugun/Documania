"""Aday türün onay formu taslakla dolu açılır — PRD 11.5.6 (PLAN.md §C85 "Dolu form").

Sistemin incelemesi (11.5.5, `app.catalog.propose`) adayda tam katalog kaydı taslağı
(`TypeProposal`) saklar. Onay formu (11.5.2) o taslağın **bütün** alanlarıyla açılır; İK düzeltir ve
iki aşamalı onayla kaydeder (K16, §20.6 metni değişmez). Kendiliğinden onay yoktur.

- **Taslaktan form (`proposal_form`).** Ad, dosya etiketi, ülke, açıklama, dosya türleri, sayfa
  aralığı, yüz yapısı, düzenler, Direkt Belge, Analiz, zorunlu alanlar, dönüşümler, çıktı biçimi,
  kabul kriterleri ve analizci için açıklama (`prompt_description` =
  `format_description(appearance)`, 11.3.1'in biçimi). Direkt Belge'de dönüşüm listesi boştur (K3).
  `front_back` türün sayfa aralığı düzenlerden türer (11.1.2).
- **Slug, etiket ve ülke önce hazır önerilen tür kaydından** (§C86, `app.training.known_types`):
  adayın adı ya da taslağın adı normalize edilince tek bir bilinen türe iniyorsa o türün slug'ı —
  hazır örnek klasörüyle aynı slug —, etiketi ve ülkesi (kayıtta ülke yoksa taslağınki) alınır.
  Hiçbir ad inmiyorsa addan türetilen slug bilinen bir türünse o tür eşleşmiş sayılır. Adlar
  birden çok türe iniyorsa (tek ad birden çok slug'a — "Turkish Driving License" — ya da iki ad
  farklı türlere) belirsizdir: slug boş kalır, tahmin edilmez. Eşleşen tür **katalogdaysa** slug
  boş kalır ve uyarılır: "Bu tür katalogda zaten olabilir: <slug>" (belirsizlikte adların indiği
  katalog türü varsa o da). Seçilen slug önerilen türse o klasördeki doğrulanmamış "AI kararı"
  örneklerinin sayısı (`unverified_example_count`, `example_files`) gösterilir.
- **Doğrulama (`build_entry`).** Form katalog sözleşmesinden geçer; hataya düşen her alan
  `TypeForm` varsayılanına döner ve adıyla bildirilir ("Şu alanlar önerilemedi, elle doldurun:").
  Varsayılana dönüş yeni bir tutarsızlık doğurabilir (yüz yapısı tek yüze dönünce düzenler);
  denetim form geçene ya da dönecek alan kalmayana kadar tekrarlanır. Boş slug sınamayı
  gölgelemesin diye (alan doğrulaması geçmezse alanlar arası tutarlılık hiç denetlenmez) sınama
  geçici slug'la yapılır.
- **Taslaksız aday** eski davranışla açılır: ad, dosya etiketi ve slug adayın adından, açıklama
  adayınki, yapı formun varsayılanları; önerilen tür kaydı ve katalog çakışması yine uygulanır.

Modül `app.catalog` paketinin dışa aktarımına girmez: taslak ve açıklama biçimi yapay zekâ katmanını
(`app.ai`) içe aktarır, o da bu paketi — paket başlatılırken döngü olmasın (`app.catalog.describe`
gibi). Yalnız okur; hiçbir şey yazmaz.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.type_proposal import TypeProposal
from app.catalog.describe import format_description
from app.catalog.form import TypeForm, TypeFormError, build_entry
from app.catalog.propose import SuggestedType, load_proposal
from app.catalog.schema import Sides, layout_pages
from app.db.models import CandidateDocumentType, ExampleFileRecord, ExampleLabel
from app.storage import SlugError, slugify
from app.training.known_types import KnownType, KnownTypes

FIELD_LABELS: Mapping[str, str] = {
    "slug": "Slug",
    "name": "Ad",
    "file_label": "Dosya etiketi",
    "country": "Ülke",
    "description": "Açıklama",
    "expected_file_types": "Beklenen dosya türleri",
    "expected_pages": "Beklenen sayfa sayısı",
    "sides": "Yüz yapısı",
    "front_back_layouts": "Kabul edilen düzenler",
    "direct": "Direkt Belge",
    "analyze": "Analiz",
    "required_fields": "Zorunlu alanlar",
    "allowed_conversions": "İzinli dönüşümler",
    "output_format": "Çıktı biçimi",
    "acceptance_criteria": "Kabul kriterleri",
    "prompt_description": "Analizci için açıklama",
}
"""Kayıt alanlarının formdaki adları (`catalog_type_fields.html`), `CatalogEntry` sırasıyla."""

_FORM_ATTRIBUTES = {"expected_pages": ("pages_min", "pages_max")}
"""Kayıt alanı → `TypeForm` alanları; listede olmayan aynı adı taşır."""

_SLUG = re.compile(r"[a-z][a-z0-9_]*")
_SLUG_MAX_LENGTH = 64
_PROBE_SLUG = "x"
"""Boş slug'lı formun sınandığı geçici slug (ayrılmış değil, biçime uyar)."""


@dataclass(frozen=True, slots=True)
class SuggestedForm:
    """Onay formunun açılışı ve onu açıklayan bant.

    `form` açılış değerleridir. `proposal_status`, `proposal_pages`, `proposal_generated_at` ve
    `proposal_reason` sistemin incelemesinin durumu, kullandığı örnek sayfa sayısı, zamanı ve
    (başarısızlıkta) gerekçesidir; `filled` formun taslaktan dolduğunu söyler. `unfilled` taslağın
    doğrulamadan geçmeyip varsayılana dönen alanlarının formdaki adlarıdır. `catalog_slug`
    katalogda aynı olabilecek türdür (slug o yüzden boş); `suggested_slug` önerilen tür kaydından
    seçilen slug'dır.
    """

    form: TypeForm
    filled: bool = False
    proposal_status: str | None = None
    proposal_pages: int | None = None
    proposal_generated_at: datetime | None = None
    proposal_reason: str | None = None
    unfilled: tuple[str, ...] = ()
    catalog_slug: str | None = None
    suggested_slug: str | None = None


def name_slug(name: str) -> str:
    """Addan türetilen slug; katalog slug biçimine uymuyorsa boş."""
    try:
        slug = slugify(name, "_", max_length=_SLUG_MAX_LENGTH).lower()
    except SlugError:
        return ""
    return slug if _SLUG.fullmatch(slug) else ""


def type_matches(
    known: KnownTypes, candidate: CandidateDocumentType, proposal: TypeProposal | None = None
) -> tuple[KnownType, ...]:
    """Adayın adının ve taslağın adının normalize edilince indiği bilinen türler (§C86), slug
    sırasıyla. Birden çok tür belirsizliktir: tek ad birden çok slug'a inebilir ("Turkish Driving
    License") ya da iki ad farklı türlere."""
    names = [candidate.proposed_name] + ([proposal.name] if proposal is not None else [])
    found = {match.slug: match for name in names for match in known.name_matches(name)}
    return tuple(found[slug] for slug in sorted(found))


def matched_type(
    known: KnownTypes, candidate: CandidateDocumentType, proposal: TypeProposal | None = None
) -> KnownType | None:
    """Adların indiği tek bilinen tür; eşleşme yoksa ya da belirsizse `None`."""
    matches = type_matches(known, candidate, proposal)
    return matches[0] if len(matches) == 1 else None


def suggested_type(
    known: KnownTypes, candidate: CandidateDocumentType, proposal: TypeProposal | None = None
) -> SuggestedType | None:
    """İncelemenin isteğine giren hazır önerilen tür kaydı (`read_examination(..., suggested=)`):
    ad katalog dışı bir önerilen türe iniyorsa o tür; katalog türüne inen ad katalog listesiyle
    zaten istektedir."""
    match = matched_type(known, candidate, proposal)
    if match is None or match.in_catalog:
        return None
    return SuggestedType(name=match.name, file_label=match.file_label, country=match.country_iso2)


def proposal_form(proposal: TypeProposal) -> TypeForm:
    """Taslağın bütün alanlarıyla form (slug hariç); doğrulanmamıştır."""
    layouts = tuple(layout.value for layout in proposal.front_back_layouts)
    pages = proposal.expected_pages
    if proposal.sides is Sides.FRONT_BACK:
        pages = layout_pages(proposal.front_back_layouts) or pages
    return TypeForm(
        name=proposal.name,
        file_label=proposal.file_label,
        country=proposal.country or "",
        description=proposal.description,
        expected_file_types=tuple(value.value for value in proposal.expected_file_types),
        pages_min="" if pages is None else str(pages.min),
        pages_max="" if pages is None else str(pages.max),
        sides=proposal.sides.value,
        front_back_layouts=layouts,
        direct=proposal.direct,
        analyze=proposal.analyze,
        required_fields=", ".join(proposal.required_fields),
        allowed_conversions=(
            () if proposal.direct else tuple(value.value for value in proposal.allowed_conversions)
        ),
        output_format=proposal.output_format.value,
        acceptance_criteria=proposal.acceptance_criteria,
        prompt_description=format_description(proposal.appearance),
    )


def validated_form(form: TypeForm) -> tuple[TypeForm, tuple[str, ...]]:
    """Formu `build_entry` ile sınar; hataya düşen her kayıt alanını `TypeForm` varsayılanına
    döndürür. Döner: geçen (ya da dönecek alanı kalmayan) form ve dönen alanların kayıt adları,
    `FIELD_LABELS` sırasıyla. Slug sınanmaz (geçici slug'la denenir)."""
    default = TypeForm()
    reverted: set[str] = set()
    while True:
        try:
            build_entry(replace(form, slug=_PROBE_SLUG))
        except TypeFormError as exc:
            names = [name for name in exc.problems if name in FIELD_LABELS]
            names = [name for name in names if name != "slug" and name not in reverted]
            if not names:
                break
            changes = {
                attribute: getattr(default, attribute)
                for name in names
                for attribute in _FORM_ATTRIBUTES.get(name, (name,))
            }
            form = replace(form, **changes)
            reverted.update(names)
            continue
        break
    return form, tuple(name for name in FIELD_LABELS if name in reverted)


def prefill_form(
    candidate: CandidateDocumentType,
    proposal: TypeProposal | None,
    *,
    known: KnownTypes | None = None,
) -> SuggestedForm:
    """Onay formunun açılışı (modül açıklaması). `known` verilmezse önerilen tür kaydı ve katalog
    çakışması uygulanmaz."""
    stored = candidate.proposal_json if isinstance(candidate.proposal_json, Mapping) else {}
    pages = stored.get("pages")
    reason = stored.get("reason")
    if proposal is None:
        name = candidate.proposed_name
        form = TypeForm(name=name, file_label=name, description=candidate.description or "")
        unfilled: tuple[str, ...] = ()
    else:
        form, unfilled = validated_form(proposal_form(proposal))
    slug = name_slug(form.name or candidate.proposed_name)
    matches: tuple[KnownType, ...] = ()
    if known is not None:
        matches = type_matches(known, candidate, proposal)
        if not matches and slug and (existing := known.get(slug)) is not None:
            matches = (existing,)  # Addan türeyen slug bilinen bir türün.
    catalog_slug = suggested_slug = None
    if len(matches) > 1:
        # Belirsiz ad: slug tahmin edilmez.
        slug = ""
        catalog_slug = next((match.slug for match in matches if match.in_catalog), None)
    elif matches and matches[0].in_catalog:
        slug, catalog_slug = "", matches[0].slug
    elif matches:
        (match,) = matches
        slug = suggested_slug = match.slug
        country = match.country_iso2 or form.country
        form = replace(form, file_label=match.file_label, country=country)
        # Kaydın etiketi ya da ülkesi taslağınkinin yerine geçti: yeniden sınanır.
        form, more = validated_form(form)
        unfilled = tuple(name for name in FIELD_LABELS if name in {*unfilled, *more})
    if not slug and catalog_slug is None and proposal is not None:
        unfilled = ("slug", *unfilled)
    return SuggestedForm(
        form=replace(form, slug=slug),
        filled=proposal is not None,
        unfilled=tuple(FIELD_LABELS[name] for name in unfilled),
        catalog_slug=catalog_slug,
        suggested_slug=suggested_slug,
        proposal_status=candidate.proposal_status,
        proposal_pages=pages if type(pages) is int else None,
        proposal_generated_at=candidate.proposal_generated_at,
        proposal_reason=reason if isinstance(reason, str) else None,
    )


def suggested_form(
    candidate: CandidateDocumentType, *, known: KnownTypes | None = None
) -> SuggestedForm:
    """Adayda saklanan taslakla (`load_proposal`; hazır değilse taslaksız) onay formunun
    açılışı."""
    return prefill_form(candidate, load_proposal(candidate), known=known)


def unverified_example_count(session: Session, slug: str) -> int:
    """`slug`'ın örnek klasöründeki doğrulanmamış "AI kararı" (`ai_decision`) örneklerinin sayısı
    (`example_files`, §C86)."""
    count = session.scalar(
        select(func.count())
        .select_from(ExampleFileRecord)
        .where(
            ExampleFileRecord.type_slug == slug,
            ExampleFileRecord.label == ExampleLabel.AI_DECISION.value,
        )
    )
    return count or 0
