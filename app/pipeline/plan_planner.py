"""Candidate decisions and deterministic assembly of planned work items."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import partial

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.photo_check import PhotoCheck
from app.ai.schemas import PageAnalysis
from app.catalog import Catalog, CatalogEntry
from app.catalog.photo_rules import PHOTO_RULE_TYPES, enabled_photo_rules
from app.db.models import Employee, QueueKind, Upload, UploadFile
from app.events import EventType, record_event
from app.matching.contacts import accumulate_contacts
from app.matching.context import context_person_verdict
from app.matching.fields import complete_profile_fields
from app.matching.match import (
    EmployeeAction,
    EmployeeMatch,
    MatchRule,
    PersonKey,
    UnmatchedResolution,
    UnmatchedRule,
    accumulate_identity,
    build_person_key,
    create_employee,
    match_employee,
    propose_pending_profile,
    resolve_unmatched,
)
from app.matching.mrz import apply_mrz_priority
from app.matching.status import inactive_employee_reason, is_inactive
from app.pipeline.group import (
    AttachmentFile,
    CandidatePage,
    DocumentCandidate,
    FileGrouping,
    UploadGrouping,
)
from app.pipeline.legibility import check_legibility
from app.pipeline.validate import (
    Validation,
    ValidationName,
    check_context_person,
    check_direct_single_source,
    check_dob_plausible,
    check_file_type,
    check_mrz_checksum,
    check_page_count,
    check_required_fields,
    check_sides,
)
from app.storage import (
    DataLayout,
    FileKind,
    UnsupportedFileTypeError,
    detect_file_kind,
    document_stem,
    sequenced_filename,
)

from .plan_models import Operation, PlanEmployee, PlanItem, PlanSource, PlanValidation, Route
from .plan_rules import (
    DirectFileTypeMismatch,
    DirectOperationForbidden,
    NoApplicableOperation,
    OperationSource,
    PhotoRulesNotMet,
    SelectedOperation,
    _pages_text,
    check_conversion,
    check_direct_file_types,
    check_direct_operation,
    check_photo_rules,
    operation_source,
    select_operation,
)


@dataclass(frozen=True, slots=True)
class _Verdict:
    """Öğeyi kuyruğa gönderen hüküm ve kişisel değer taşımayan gerekçesi."""

    queue: QueueKind
    reason: str


@dataclass(frozen=True, slots=True)
class _Ownerless:
    """Belge düzeyinde kabul edilmiş, kişi taşımayan türün §20.2.2 satır 8 adayı: sahibi bulunursa
    öğeyi yeniden kurmak için gerekenler (D29)."""

    sources: tuple[PlanSource, ...]
    entry: CatalogEntry
    selected: SelectedOperation | None
    validations: tuple[Validation, ...]


_NO_EMPLOYEE = PlanEmployee(action=EmployeeAction.NONE, employee_id=None, matched_by=None)

_Subject = tuple[tuple[int, int], Callable[[str], PlanItem]]


class _Planner:
    """Tek planlamanın durumu: gruplama, katalog, referans gün ve dosya biçimi önbelleği."""

    def __init__(
        self,
        session: Session,
        layout: DataLayout,
        upload: Upload,
        grouping: UploadGrouping,
        *,
        catalog: Catalog,
        today: date,
    ) -> None:
        self._session = session
        self._layout = layout
        self._upload = upload
        self._grouping = grouping
        self._catalog = catalog
        self._today = today
        self._files = {upload_file.id: upload_file for upload_file in upload.files}
        self._blank_pages = {
            file_grouping.file_id: frozenset(file_grouping.blank_pages)
            for file_grouping in grouping.files
        }
        self._kinds: dict[int, FileKind | None] = {}
        # Kişi anahtarı bir şey okumuş adaylar ve sahibi aynı dosyadan aranacak kişisiz adaylar.
        self._person_items: set[str] = set()
        self._ownerless: dict[str, _Ownerless] = {}

    def items(self) -> tuple[PlanItem, ...]:
        # Kararlar öğe sırasıyla verilir: yan etki (yeni çalışan) sonraki öğenin kararına girer.
        subjects = sorted(self._subjects(self._grouping), key=lambda subject: subject[0])
        items = [build(f"i{number}") for number, (_, build) in enumerate(subjects, start=1)]
        # İkinci geçiş: kişi taşımayan adayın sahibi, dosyadaki kimlikli adayların hükmü belli
        # olduktan sonra bulunur; öğe kimlikleri ve sırası değişmez.
        return tuple(self._owned(item, items) for item in items)

    def _subjects(self, grouping: UploadGrouping) -> Iterator[_Subject]:
        for candidate in grouping.candidates:
            first = candidate.pages[0]
            yield (first.file_id, first.index), partial(self._candidate_item, candidate=candidate)
        for file_grouping in grouping.files:
            yield from _page_subjects(file_grouping)
        attached = {attachment.file_id for attachment in grouping.attachments}
        for attachment in grouping.attachments:
            yield (attachment.file_id, -1), partial(self._attachment_item, attachment=attachment)
        for upload_file in self._upload.files:
            duplicate = upload_file.is_duplicate_of is not None
            if duplicate or (not upload_file.pages and upload_file.id not in attached):
                yield (upload_file.id, -1), partial(_file_item, upload_file=upload_file)

    # --- belge adayı --------------------------------------------------------------------------

    def _candidate_item(self, item_id: str, *, candidate: DocumentCandidate) -> PlanItem:
        # MRZ önce (K6, 05.3.3): okunaklılık kapısı ve kişi anahtarı MRZ'nin çözdüğü okumayı görür.
        candidate = replace(
            candidate, pages=tuple(self._mrz_resolved(page) for page in candidate.pages)
        )
        analyses = [page.analysis for page in candidate.pages]
        first = candidate.pages[0]
        key = build_person_key(analyses, today=self._today)
        match = match_employee(self._session, key, file_id=first.file_id, page_index=first.index)
        nobody = _reads_no_person(key, match)
        if not nobody:
            self._person_items.add(item_id)
        entry = self._entry(candidate)
        sources = tuple(
            PlanSource(
                file_id=file_id,
                pages=tuple(page.index for page in candidate.pages if page.file_id == file_id),
            )
            for file_id in candidate.file_ids
        )
        verdicts, selected, validations = self._document_verdicts(candidate, entry, sources, key)
        if entry is None or verdicts:
            # Belge kabul edilmedi: eşleştirme hükmü yalnız kişi tahminidir, yan etki yok. Bağlam
            # çalışanına ait görünmeyen belgenin kişi tahmini de yoktur (10.5.5).
            guess = _verdict_of(match)
            if guess is not None:
                verdicts.append(guess)
            foreign = _foreign(validations)
            employee = _NO_EMPLOYEE if foreign else _employee_guess(match)
            inactive = None if foreign else self._inactive_verdict(match.employee_id)
            if inactive is not None:
                verdicts.append(inactive)
            return self._item(item_id, sources, entry, employee, verdicts, None, validations)
        employee, verdict = self._decide_employee(key, match, entry, analyses, first)
        verdicts = [] if verdict is None else [verdict]
        if nobody and not entry.required_fields:
            # Kişi taşımayan türün satır 8 adayı: sahibi ikinci geçişte aynı dosyadan aranır.
            self._ownerless[item_id] = _Ownerless(sources, entry, selected, validations)
        return self._item(item_id, sources, entry, employee, verdicts, selected, validations)

    def _owned(self, item: PlanItem, items: Sequence[PlanItem]) -> PlanItem:
        # Kişisiz adayın sahibi bulunursa öğe Hazir'a o çalışanla yeniden kurulur; hükmü yalnız
        # satır 8'di (belge düzeyinde kabul), başka ret gerekçesi yok. Kimlik ve iletişim bilgisi
        # birikmez: belgede kişi anahtarı yoktur.
        ownerless = self._ownerless.get(item.item_id)
        owner = None if ownerless is None else self._file_owner(ownerless.sources, items)
        if ownerless is None or owner is None:
            return item
        employee = PlanEmployee(action=EmployeeAction.MATCH, employee_id=owner, matched_by=None)
        return self._item(
            item.item_id,
            ownerless.sources,
            ownerless.entry,
            employee,
            [],
            ownerless.selected,
            ownerless.validations,
        )

    def _file_owner(self, sources: Sequence[PlanSource], items: Sequence[PlanItem]) -> str | None:
        # Aynı yüklenen dosyadaki kimlikli adayların hepsi — Hazir'a gideni de kuyruğa gideni de —
        # tek bir kayıtlı çalışana satır 1/3 ile bağlıysa (kuyruktakinde kişi tahmini) ve en az
        # biri Hazir'a gidiyorsa sahip odur. Yeni açılan çalışan, onay bekleyen profil, belirsiz
        # ya da yalnız isim hükmü ve ikinci bir çalışan sahip vermez.
        files = {source.file_id for source in sources}
        people = [
            other
            for other in items
            if other.item_id in self._person_items
            and files.intersection(source.file_id for source in other.sources)
        ]
        owners = {
            other.employee.employee_id if other.employee.matched_by is not None else None
            for other in people
        }
        if len(owners) != 1 or not any(other.route is Route.READY for other in people):
            return None
        (owner,) = owners
        return owner

    def _mrz_resolved(self, page: CandidatePage) -> CandidatePage:
        return replace(page, analysis=apply_mrz_priority(page.analysis, today=self._today).analysis)

    def _entry(self, candidate: DocumentCandidate) -> CatalogEntry | None:
        slug = candidate.document_type_slug
        if candidate.unknown_type is not None or slug is None:
            return None
        return self._catalog.get(slug)

    def _document_verdicts(
        self,
        candidate: DocumentCandidate,
        entry: CatalogEntry | None,
        sources: Sequence[PlanSource],
        key: PersonKey,
    ) -> tuple[list[_Verdict], SelectedOperation | None, tuple[Validation, ...]]:
        # Belge düzeyindeki hükümler (çalışan kararından önce), kabul edilen belgenin işlemi ve
        # doğrulamalar (06.5.1).
        unknown = candidate.unknown_type
        if unknown is not None:
            return [_Verdict(unknown.queue, unknown.reason)], None, ()
        structural = [
            _Verdict(verdict.queue, verdict.reason)
            for verdict in (candidate.contiguity_violation, candidate.ambiguous_pairing)
            if verdict is not None
        ]
        if structural or entry is None:
            return structural, None, ()
        shape = (
            Validation(ValidationName.PAGE_COUNT, check_page_count(candidate)),
            Validation(ValidationName.SIDES, check_sides(candidate, entry=entry)),
        )
        if not all(validation.ok for validation in shape):
            # Eksik ya da parça belge: okunaklılık, öteki doğrulayıcılar ve işlem uygulanmaz.
            return _failed(shape), None, shape
        check = check_legibility(candidate, catalog=self._catalog)
        operation_sources = [self._operation_source(source) for source in sources]
        single_source, file_type = self._source_validations(entry, operation_sources)
        required = Validation(ValidationName.REQUIRED_FIELDS, check_required_fields(check))
        content = (
            Validation(
                ValidationName.MRZ_CHECKSUM, check_mrz_checksum(candidate, today=self._today)
            ),
            Validation(
                ValidationName.DOB_PLAUSIBLE,
                check_dob_plausible(key.date_of_birth, today=self._today),
            ),
            *self._context_person(key, entry),
        )
        unmet = None if check is None else check.unmet_criteria
        photo = self._photo_rules_not_met(candidate, entry)
        verdicts = [
            *_failed((required,)),
            *([] if unmet is None else [_Verdict(unmet.queue, unmet.reason)]),
            *_failed((single_source, file_type, *content)),
            *([] if photo is None else [_Verdict(photo.queue, photo.reason)]),
        ]
        selected, refusal = self._checked_operation(
            entry, operation_sources, (single_source, file_type)
        )
        validations = (required, *shape, single_source, file_type, *content)
        return [*verdicts, *refusal], selected, validations

    def _context_person(self, key: PersonKey, entry: CatalogEntry) -> tuple[Validation, ...]:
        # 10.5.5: yalnız bağlam çalışanlı yüklemede; bağlamsız partinin öğesi bu doğrulamayı
        # taşımaz.
        employee_id = self._upload.context_employee_id
        if employee_id is None:
            return ()
        verdict = context_person_verdict(self._session, key, entry=entry, employee_id=employee_id)
        return (Validation(ValidationName.CONTEXT_PERSON, check_context_person(verdict)),)

    def _photo_rules_not_met(
        self, candidate: DocumentCandidate, entry: CatalogEntry
    ) -> PhotoRulesNotMet | None:
        # 11.7.1: türün planlama anındaki açık kuralları, sayfalara analizde saklanan kontrolle.
        if entry.slug not in PHOTO_RULE_TYPES:
            return None
        rules = enabled_photo_rules(entry.photo_rules)
        if not rules:
            return None
        checks = [self._stored_photo_check(page.file_id, page.index) for page in candidate.pages]
        return check_photo_rules(rules, checks)

    def _stored_photo_check(self, file_id: int, index: int) -> PhotoCheck | None:
        page = next((row for row in self._files[file_id].pages if row.index == index), None)
        if page is None or page.photo_check_json is None:
            return None
        try:
            return PhotoCheck.model_validate(page.photo_check_json)
        except ValidationError:
            # Okunamayan kayıt değerlendirme sayılmaz: kuralları değerlendirilmemiştir.
            return None

    def _decide_employee(
        self,
        key: PersonKey,
        match: EmployeeMatch,
        entry: CatalogEntry,
        analyses: Sequence[PageAnalysis],
        first: CandidatePage,
    ) -> tuple[PlanEmployee, _Verdict | None]:
        session = self._session
        inactive = self._inactive_verdict(match.employee_id)
        if inactive is not None:
            # 10.5.7: pasif çalışan bulunur ama belge otomatik yerleşmez (R7); çalışan kişi
            # tahminidir, kimlik, profil alanı ve iletişim bilgisi birikmez.
            return _employee_guess(match), inactive
        if match.employee_id is not None:
            # §20.2.2 satır 1/3: yeni yazım, temiz numara, boş profil alanı ve iletişim bilgisi
            # birikir.
            accumulate_identity(session, key, entry=entry)
            complete_profile_fields(
                session,
                key,
                employee_id=match.employee_id,
                file_id=first.file_id,
                page_index=first.index,
            )
            accumulate_contacts(session, match.employee_id, analyses)
            employee = PlanEmployee(
                action=EmployeeAction.MATCH,
                employee_id=match.employee_id,
                matched_by=match.matched_by,
            )
            return employee, None
        if match.rule is not MatchRule.NO_MATCH:
            # Çelişkili anahtar, belirsiz eşleşme, yalnız isim (satır 2, 4, 5): yalnız adla eşleşme
            # yeni çalışan açmaz (R8), satır 6b'ye inilmez.
            return _NO_EMPLOYEE, _verdict_of(match)
        # Satır 6 (temiz numara) ya da 6b (Latin ad-soyad + doğum tarihi, §20.2.4): ikisi de
        # `employee.action: create`; dayanak `EMPLOYEE_CREATED` verisindedir. Makul yaş partinin
        # alındığı güne göredir (`dob_plausible` doğrulayıcısıyla aynı gün).
        resolution = resolve_unmatched(key, match, entry=entry, today=self._today)
        if resolution.rule is UnmatchedRule.CREATE:
            created = create_employee(
                session,
                self._layout,
                key,
                entry=entry,
                today=self._today,
                file_id=first.file_id,
                page_index=first.index,
            )
            complete_profile_fields(
                session,
                key,
                employee_id=created.id,
                file_id=first.file_id,
                page_index=first.index,
                created=True,
            )
            accumulate_contacts(session, created.id, analyses)
            employee = PlanEmployee(
                action=EmployeeAction.CREATE, employee_id=created.id, matched_by=None
            )
            return employee, None
        if resolution.rule is UnmatchedRule.PENDING_PROFILE:
            propose_pending_profile(
                session,
                key,
                entry=entry,
                today=self._today,
                file_id=first.file_id,
                page_index=first.index,
            )
        employee = PlanEmployee(action=resolution.action, employee_id=None, matched_by=None)
        return employee, _verdict_of(resolution)

    def _inactive_verdict(self, employee_id: str | None) -> _Verdict | None:
        # 10.5.7 (§20.2.2 notu): pasif çalışana belge otomatik yerleşmez; gerekçe kod ve E
        # numarasıdır. Durum planlama anında okunur: plan donar (K9), yeniden çalıştırma aynı
        # kararı uygular, etkinleştirmenin etkisi yeniden analizle gelir.
        if employee_id is None:
            return None
        employee = self._session.get(Employee, employee_id)
        if employee is None or not is_inactive(employee):
            return None
        return _Verdict(QueueKind.UNRESOLVED, inactive_employee_reason(employee_id))

    def _item(
        self,
        item_id: str,
        sources: tuple[PlanSource, ...],
        entry: CatalogEntry | None,
        employee: PlanEmployee,
        verdicts: Sequence[_Verdict],
        selected: SelectedOperation | None,
        validations: Sequence[Validation],
    ) -> PlanItem:
        slug = None if entry is None else entry.slug
        if entry is not None:
            self._record_validation_failures(item_id, entry, sources[0], validations)
        checked = tuple(
            PlanValidation(name=validation.name, ok=validation.ok) for validation in validations
        )
        if verdicts or entry is None or selected is None or employee.employee_id is None:
            return _queued_item(item_id, slug, sources, employee, verdicts, checked)
        owner = self._session.get_one(Employee, employee.employee_id)
        stem = document_stem(owner.given_names, owner.surname, entry.file_label)
        return PlanItem(
            item_id=item_id,
            document_type_slug=slug,
            sources=sources,
            operation=selected.operation,
            target_format=selected.target_format,
            target_name=sequenced_filename(stem, 1, selected.target_format.value),
            employee=employee,
            route=Route.READY,
            route_reason=None,
            validations=checked,
        )

    def _record_validation_failures(
        self,
        item_id: str,
        entry: CatalogEntry,
        first: PlanSource,
        validations: Sequence[Validation],
    ) -> None:
        # 06.5.2: her geçmeyen doğrulama öğenin ilk sayfasıyla (ekte dosyasıyla) loga yazılır.
        for validation in validations:
            failure = validation.failure
            if failure is None:
                continue
            record_event(
                self._session,
                EventType.VALIDATION_FAILED,
                file_id=first.file_id,
                page_index=first.pages[0] if first.pages else None,
                message=failure.reason,
                data={
                    "item_id": item_id,
                    "validation": validation.name.value,
                    "document_type_slug": entry.slug,
                    "queue": failure.queue.value,
                },
            )

    # --- Word/Excel eki -----------------------------------------------------------------------

    def _attachment_item(self, item_id: str, *, attachment: AttachmentFile) -> PlanItem:
        # K2: sayfası ve analizi olmayan ek yalnız kaynak doğrulayıcılarından geçer.
        sources = (PlanSource(file_id=attachment.file_id, pages=()),)
        entry = self._catalog.get(attachment.document_type_slug)
        operation_sources = [self._operation_source(source) for source in sources]
        validations = self._source_validations(entry, operation_sources)
        selected, refusal = self._checked_operation(entry, operation_sources, validations)
        verdicts = [*_failed(validations), *refusal]
        unresolved = attachment.unresolved
        if unresolved is not None:
            # Bağlam çalışanı olmadan yüklenen ekin sahibi belirsizdir.
            verdicts.append(_Verdict(unresolved.queue, unresolved.reason))
            return self._item(
                item_id, sources, entry, _NO_EMPLOYEE, verdicts, selected, validations
            )
        # Sahibi partinin bağlam çalışanıdır (`unresolved` boşsa doludur); belge kimliğiyle
        # eşleştirilmedi, `matched_by` boş kalır. Bağlam çalışanı yüklemeden sonra pasife
        # alındıysa ek de otomatik yerleşmez (10.5.7).
        owner = self._upload.context_employee_id
        employee = PlanEmployee(action=EmployeeAction.MATCH, employee_id=owner, matched_by=None)
        inactive = self._inactive_verdict(owner)
        if inactive is not None:
            verdicts.append(inactive)
        return self._item(item_id, sources, entry, employee, verdicts, selected, validations)

    # --- işlem --------------------------------------------------------------------------------

    def _source_validations(
        self, entry: CatalogEntry, sources: Sequence[OperationSource]
    ) -> tuple[Validation, Validation]:
        # `direct_single_source` ve `file_type` (06.5.1). Direkt Belge'de `file_type` §20.4.1'in
        # format kontrolüdür: gerekçesi o bölümün, reddi `DIRECT_DOC_CHECK`'e de yazılır (06.3.2).
        single_source = check_direct_single_source(sources, entry=entry)
        if entry.direct:
            mismatch = check_direct_file_types(sources, entry=entry)
            if mismatch is not None:
                self._record_direct_refusal(entry, sources, mismatch, operation=None)
        else:
            mismatch = check_file_type(sources, entry=entry)
        return (
            Validation(ValidationName.DIRECT_SINGLE_SOURCE, single_source),
            Validation(ValidationName.FILE_TYPE, mismatch),
        )

    def _checked_operation(
        self,
        entry: CatalogEntry,
        operation_sources: Sequence[OperationSource],
        source_validations: Sequence[Validation],
    ) -> tuple[SelectedOperation | None, list[_Verdict]]:
        # İşlem yalnız kaynak doğrulayıcılarından geçen belgede seçilir; geçmeyenin hükmü onundur.
        if not all(validation.ok for validation in source_validations):
            return None, []
        return self._operation(entry, operation_sources)

    def _operation(
        self, entry: CatalogEntry, operation_sources: Sequence[OperationSource]
    ) -> tuple[SelectedOperation | None, list[_Verdict]]:
        # Kaynak doğrulamasından geçen belgede §20.3 → Direkt Belge matrisi (06.3.1) → dönüşüm
        # izni (06.4.1). İlk ret sonraki adımı keser: işlem yok ve belgeyi Unresolved'a gönderen
        # tek hüküm.
        selection = select_operation(operation_sources, output_format=entry.output_format)
        if isinstance(selection, NoApplicableOperation):
            return None, [_Verdict(selection.queue, selection.reason)]
        forbidden = check_direct_operation(selection.operation, entry=entry)
        if forbidden is not None:
            self._record_direct_refusal(
                entry, operation_sources, forbidden, operation=selection.operation
            )
            return None, [_Verdict(forbidden.queue, forbidden.reason)]
        not_allowed = check_conversion(selection.operation, entry=entry)
        if not_allowed is not None:
            return None, [_Verdict(not_allowed.queue, not_allowed.reason)]
        return selection, []

    def _record_direct_refusal(
        self,
        entry: CatalogEntry,
        sources: Sequence[OperationSource],
        refusal: DirectFileTypeMismatch | DirectOperationForbidden,
        *,
        operation: Operation | None,
    ) -> None:
        # §20.4: ret `DIRECT_DOC_CHECK`'e adayın ilk sayfasıyla (ekte dosyayla) yazılır.
        first = sources[0]
        record_event(
            self._session,
            EventType.DIRECT_DOC_CHECK,
            file_id=first.file_id,
            page_index=first.pages[0] if first.pages else None,
            message=refusal.reason,
            data={
                "document_type_slug": entry.slug,
                "check": refusal.check,
                "operation": None if operation is None else operation.value,
                "expected_file_types": [file_type.value for file_type in entry.expected_file_types],
                "file_types": [
                    None if source.kind is None else source.kind.value for source in sources
                ],
                "queue": refusal.queue.value,
            },
        )

    def _operation_source(self, source: PlanSource) -> OperationSource:
        return operation_source(
            self._files[source.file_id],
            source,
            kind=self._file_kind(source.file_id),
            blank_pages=self._blank_pages.get(source.file_id, frozenset()),
        )

    def _file_kind(self, file_id: int) -> FileKind | None:
        # Biçim içerikten okunur (01.2.1); istemcinin bildirdiği `mime`'a güvenilmez.
        if file_id not in self._kinds:
            upload_file = self._files[file_id]
            content = self._layout.resolve(upload_file.stored_path).read_bytes()
            try:
                self._kinds[file_id] = detect_file_kind(content)
            except UnsupportedFileTypeError:
                self._kinds[file_id] = None
        return self._kinds[file_id]


def _failed(validations: Iterable[Validation]) -> list[_Verdict]:
    # Geçmeyen doğrulamaların hükümleri, doğrulayıcı sırasıyla (06.5.2).
    return [
        _Verdict(validation.failure.queue, validation.failure.reason)
        for validation in validations
        if validation.failure is not None
    ]


def _verdict_of(decision: EmployeeMatch | UnmatchedResolution) -> _Verdict | None:
    # Çalışan kararı belgeyi kuyruğa gönderiyorsa hüküm; Hazir'a giden kararda `None`.
    if decision.queue is None or decision.reason is None:
        return None
    return _Verdict(decision.queue, decision.reason)


def _foreign(validations: Iterable[Validation]) -> bool:
    # 10.5.5: belge bağlam çalışanına ait görünmüyor (`context_person` geçmedi).
    return any(
        validation.name is ValidationName.CONTEXT_PERSON and not validation.ok
        for validation in validations
    )


def _reads_no_person(key: PersonKey, match: EmployeeMatch) -> bool:
    # §20.2.2 satır 8'in koşulu (`resolve_unmatched`'in `NO_PERSON`'ı): eşleşme yok ve anahtar ne
    # belge numarası, ne isim anahtarı, ne ad ya da soyad okumuş.
    return match.rule is MatchRule.NO_MATCH and not (
        key.document_numbers
        or key.name_keys
        or key.surname is not None
        or key.given_names is not None
    )


def _employee_guess(match: EmployeeMatch) -> PlanEmployee:
    # Kuyruğa giden belgenin kişi tahmini (08.1.2): yalnız satır 1/3'ün çalışanı.
    if match.employee_id is None:
        return _NO_EMPLOYEE
    return PlanEmployee(
        action=EmployeeAction.MATCH, employee_id=match.employee_id, matched_by=match.matched_by
    )


def _queued_item(
    item_id: str,
    slug: str | None,
    sources: tuple[PlanSource, ...],
    employee: PlanEmployee,
    verdicts: Sequence[_Verdict],
    validations: tuple[PlanValidation, ...],
) -> PlanItem:
    return PlanItem(
        item_id=item_id,
        document_type_slug=slug,
        sources=sources,
        operation=None,
        target_format=None,
        target_name=None,
        employee=employee,
        route=Route(verdicts[0].queue.value),
        route_reason=" ".join(verdict.reason for verdict in verdicts),
        validations=validations,
    )


_BLANK_PAGES_REASON = "Boş sayfa ({pages}): atlanır; çıktıya ve kuyruğa girmez, hata sayılmaz."

_UNANALYZED_PAGES_REASON = (
    "Analizi yapılamamış sayfa ({pages}): içeriği bilinmediği için hiçbir belgeye katılmaz ve "
    "çıktı üretmez (R7); yeniden analizle değerlendirilir."
)


def _page_subjects(grouping: FileGrouping) -> Iterator[_Subject]:
    # Adaya girmeyen sayfalar: boş sayfa atlanır (S8), analizi olmayan sayfa kuyruğa gider (R7).
    file_id = grouping.file_id
    for pages, route, reason in (
        (grouping.blank_pages, Route.SKIP, _BLANK_PAGES_REASON),
        (grouping.unanalyzed_pages, Route.UNRESOLVED, _UNANALYZED_PAGES_REASON),
    ):
        if pages:
            ordered = tuple(sorted(pages))
            build = partial(
                _unowned_item,
                file_id=file_id,
                pages=ordered,
                route=route,
                reason=reason.format(pages=_pages_text(file_id, ordered)),
            )
            yield (file_id, ordered[0]), build


def _file_item(item_id: str, *, upload_file: UploadFile) -> PlanItem:
    # Bütün olarak ele alınan dosya: tekrar yükleme ya da sayfası üretilmemiş, tanınmayan dosya.
    if upload_file.is_duplicate_of is not None:
        route = Route.SKIP
        reason = (
            f"Tekrar yükleme (01.4.1): dosya {upload_file.id}, daha önce yüklenen dosya "
            f"{upload_file.is_duplicate_of} ile aynı içerikte; yeniden işlenmez, çıktı üretmez."
        )
    else:
        route = Route.UNRESOLVED
        reason = (
            f"İşlenemeyen dosya (dosya {upload_file.id}): sayfası üretilmemiş ve Word/Excel eki "
            "olarak tanınmadı; çıktı üretmez (R7)."
        )
    return _unowned_item(item_id, file_id=upload_file.id, pages=(), route=route, reason=reason)


def _unowned_item(
    item_id: str, *, file_id: int, pages: tuple[int, ...], route: Route, reason: str
) -> PlanItem:
    return PlanItem(
        item_id=item_id,
        document_type_slug=None,
        sources=(PlanSource(file_id=file_id, pages=pages),),
        operation=None,
        target_format=None,
        target_name=None,
        employee=_NO_EMPLOYEE,
        route=route,
        route_reason=reason,
        validations=(),
    )
