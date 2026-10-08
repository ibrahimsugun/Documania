"""Profil alanlarını geçmiş belgelerden tamamlama — PRD 05.7.3 (PLAN.md §C82).

05.7.3'ten önce işlenmiş belgeler profil alanlarını yalnız çalışan açılırken doldurmuştu; sonraki
eşleşmelerde boş kalan doğum tarihi, uyruk, diğer isimler ya da orijinal yazım dolmadı ve hiçbir
alanın kaynağı kayıtlı değildi. `fill_profile_fields` mevcut çalışanların **etkin** belgelerini
(eski sürüm ve arşivlenmiş belge çalışanın klasöründe durmaz) boru hattının kuralıyla
(`app.matching.fields.complete_profile_fields`) işler:

1. Çalışanlar E numarası sırasıyla, her çalışanın belgeleri **en eski önce** (oluşturulma zamanı,
   sonra kimlik) — boş alan onu ilk okuyan belgeden dolar.
2. Belgenin kişi anahtarı (05.4.1) kaynak sayfalarının saklanan analizlerinden, belgenin kökeni
   (`documents.source_refs_json`) sırasıyla kurulur; MRZ doğum tarihinin yüzyılı kaynağın
   yüklendiği günle seçilir (§20.1.6), planlayıcı gibi. Analizi olmayan (Word/Excel eki) ya da
   sayfalarından biri okunamayan (analiz yok, şemaya uymuyor) belge atlanır.
3. Kaynak belgenin ilk sayfasıdır; aynı kaynaktan daha önce gözlenmiş alan atlanır. Bu yüzden
   komut tekrar çalıştırılabilir: ikinci çalıştırma alan, gözlem ya da olay yazmaz; boru hattının
   bu kuraldan sonra işlediği belgeler de yeniden sayılmaz.
4. Planın yalnız isimle yerleştirdiği belge (§20.2.2 satır 5a, `matched_by: name`; 05.5.4,
   `app.pipeline.plan_models.name_matched_documents`) atlanır: boru hattında olduğu gibi profil
   alanı doldurmaz, gözlem yazmaz.

Olaylar (`EMPLOYEE_FIELD_FILLED`) verilen kullanıcı adıyla ve belge kimliğiyle yazılır. Klasör ve
dosya adları (K8), eşleştirme anahtarı, isim yazımları ve belge içeriği değişmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import PageAnalysis
from app.db.models import Document, DocumentStatus, Employee, Page, ProfileField, UploadFile
from app.matching.fields import FieldCompletion, complete_profile_fields
from app.matching.match import build_person_key
from app.pipeline.analyze import PageAnalysisStatus
from app.pipeline.plan_models import name_matched_documents


@dataclass(frozen=True, slots=True)
class ProfileFieldFill:
    """Bir çalışanın geçmiş belgelerinden tamamlanması: `filled` doldurulan, `conflicts` belgede
    farklı değer okunan alanlar (`ProfileField` sırasıyla, tekrarsız); `documents` işlenen belge
    sayısı. Kişisel değer taşımaz."""

    employee_id: str
    documents: int
    filled: tuple[str, ...]
    conflicts: tuple[str, ...]


def fill_profile_fields(session: Session, *, actor: str = "system") -> list[ProfileFieldFill]:
    """Mevcut çalışanların etkin belgeleriyle boş profil alanlarını doldurur (E numarası sırasıyla).

    Dönen liste yalnız en az bir belgesi işlenen çalışanlardır. Oturum commit edilmez: çağıran
    commit eder ya da (yalnız ne yapılacağını görmek için) geri alır.
    """
    employees = session.scalars(select(Employee)).all()
    fills = []
    # E numarası sırası (`E9999` < `E10000`).
    for employee in sorted(employees, key=lambda each: (len(each.id), each.id)):
        completions = [
            completion
            for document in _active_documents(session, employee.id)
            if (completion := _complete(session, document, actor=actor)) is not None
        ]
        if completions:
            fills.append(_summary(employee.id, completions))
    return fills


def _active_documents(session: Session, employee_id: str) -> list[Document]:
    documents = list(
        session.scalars(
            select(Document)
            .where(
                Document.employee_id == employee_id,
                Document.status == DocumentStatus.ACTIVE.value,
            )
            .order_by(Document.created_at, Document.id)
        )
    )
    # 05.5.4: isimle yerleşen belge kimlik ve profil alanı biriktirmez.
    by_name = name_matched_documents(documents)
    return [document for document in documents if document.id not in by_name]


def _complete(session: Session, document: Document, *, actor: str) -> FieldCompletion | None:
    refs = _refs(document.source_refs_json)
    if not refs or not refs[0][1]:
        return None
    analyses = _analyses(session, refs)
    if analyses is None:
        return None
    file_id, pages = refs[0]
    upload_file = session.get_one(UploadFile, file_id)
    key = build_person_key(analyses, today=_upload_day(upload_file))
    return complete_profile_fields(
        session,
        key,
        employee_id=document.employee_id,
        file_id=file_id,
        page_index=pages[0],
        document_id=document.id,
        actor=actor,
    )


def _refs(source_refs: Any) -> list[tuple[int, tuple[int, ...]]]:
    # `documents.source_refs_json`: `[{"file_id": 4, "pages": [0, 1]}]`, planın sırasıyla (K15).
    # Bozuk kayıt belgeyi atlatır: kaynağı belli olmayan okuma alana yazılmaz.
    if not isinstance(source_refs, list):
        return []
    refs = []
    for ref in source_refs:
        file_id = ref.get("file_id") if isinstance(ref, dict) else None
        pages = ref.get("pages") if isinstance(ref, dict) else None
        if not isinstance(file_id, int) or not isinstance(pages, list):
            return []
        if not all(isinstance(index, int) for index in pages):
            return []
        refs.append((file_id, tuple(pages)))
    return refs


def _analyses(
    session: Session, refs: list[tuple[int, tuple[int, ...]]]
) -> list[PageAnalysis] | None:
    # Kaynak sayfaların saklanan analizleri, köken sırasıyla — katalogsuz okunur (C12). Bir sayfa
    # okunamıyorsa belge atlanır: eksik okumayla kurulan anahtar alanı yanlış doldurabilir.
    analyses = []
    for file_id, pages in refs:
        for index in pages:
            page = session.scalar(select(Page).where(Page.file_id == file_id, Page.index == index))
            if (
                page is None
                or page.analysis_status != PageAnalysisStatus.DONE
                or page.analysis_json is None
            ):
                return None
            try:
                analyses.append(PageAnalysis.model_validate(page.analysis_json))
            except ValidationError:
                return None
    return analyses


def _upload_day(upload_file: UploadFile) -> date:
    return upload_file.upload.created_at.date()


def _summary(employee_id: str, completions: list[FieldCompletion]) -> ProfileFieldFill:
    filled = {name for completion in completions for name in completion.filled}
    conflicts = {name for completion in completions for name in completion.conflicts}
    return ProfileFieldFill(
        employee_id=employee_id,
        documents=len(completions),
        filled=tuple(field.value for field in ProfileField if field.value in filled),
        conflicts=tuple(field.value for field in ProfileField if field.value in conflicts),
    )
