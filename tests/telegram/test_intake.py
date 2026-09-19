"""12.2.1–12.2.3 — Telegram'dan belge alma, albümü tek parti sayma ve sonuç özeti.

Bot gerçek `Application` + gerçek `DocumentIntake` ile kurulur; yalnız Telegram aktarıcısı
(`FakeTelegram`) ve yapay zekâ sağlayıcısı (kayıtlı yanıtlar) sahtedir. Belgeler
`tests/fixtures/gen.py`'nin sentetik sayfalarıdır (CONVENTIONS §6).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker
from telegram import Update

from app.ai.recording_provider import RecordingProvider
from app.db.models import Document, Event, QueueItem, Upload, UploadFile, UploadStatus
from app.events import EventType
from app.pipeline.orchestrate import ProcessedUpload
from app.telegram import handlers
from app.telegram.handlers import (
    DOWNLOAD_FAILED_TEXT,
    FAILURE_TEXT,
    NO_OUTPUT_TEXT,
    TelegramFile,
    build_summary,
    telegram_file,
    unique_names,
)
from tests.fixtures.gen import (
    PERSON_ORNEKOVA,
    PERSON_SIDOROV,
    blank_page,
    make_document_pdf_bytes,
    make_docx_bytes,
    make_page_image_bytes,
    passport_page,
    recorded_provider,
    write_recordings,
)
from tests.telegram.conftest import (
    LISTED_ID,
    OTHER_ID,
    IntakeBot,
    document_update,
    message_update,
    photo_update,
)

DOCUMENT_NUMBER = "00 0000001"


def passport() -> object:
    return passport_page(
        PERSON_ORNEKOVA, document_number=DOCUMENT_NUMBER, expiry_date=date(2030, 1, 1)
    )


def passport_pdf() -> bytes:
    return make_document_pdf_bytes([passport()])  # type: ignore[list-item]


def provider_for(tmp_path: Path, *files: list[object]) -> RecordingProvider:
    return recorded_provider(tmp_path / "kayit", *files)  # type: ignore[arg-type]


def idle_provider(tmp_path: Path) -> RecordingProvider:
    """Hiç çağrılmaması gereken sağlayıcı (yalnız analiz edilmeyen Word ekleri gönderilir)."""
    return provider_for(tmp_path, [passport()])


@pytest.fixture
def listed(whitelist: Callable[..., None]) -> None:
    whitelist(LISTED_ID)


def all_uploads(session_factory: sessionmaker[Session]) -> list[Upload]:
    with session_factory() as session:
        query = select(Upload).options(selectinload(Upload.files)).order_by(Upload.id)
        return list(session.scalars(query))


def file_names(session_factory: sessionmaker[Session], upload_id: str) -> list[str]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(UploadFile.original_name)
                .where(UploadFile.upload_id == upload_id)
                .order_by(UploadFile.id)
            )
        )


# --- 12.2.1: web ile aynı boru hattı ------------------------------------------------------------


def test_document_goes_through_the_same_pipeline_as_a_web_upload(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    provider = provider_for(tmp_path, [passport()])
    bot = make_intake_bot(provider)
    pdf = passport_pdf()
    bot.telegram.files["f1"] = pdf

    bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))

    (upload,) = all_uploads(session_factory)
    assert (upload.channel, upload.status) == ("telegram", UploadStatus.DONE.value)
    assert upload.uploaded_by == f"ik-{LISTED_ID}"  # beyaz listedeki kullanıcının panel adı
    (stored,) = upload.files
    # K10: Inbox'taki dosya Telegram'dan gelen baytların aynısı.
    assert bot.layout is not None
    assert bot.layout.resolve(stored.stored_path).read_bytes() == pdf
    assert (stored.original_name, stored.mime) == ("pasaport.pdf", "application/pdf")
    with session_factory() as session:
        types = set(session.scalars(select(Event.type).where(Event.upload_id == upload.id)))
        assert {
            EventType.FILE_UPLOADED,
            EventType.PAGE_RENDERED,
            EventType.PAGE_ANALYZED,
            EventType.PLAN_CREATED,
            EventType.OUTPUT_SAVED,
        } <= types
        (document,) = session.scalars(select(Document)).all()
    assert document.status == "active"
    assert len(provider.requests) == 1  # sayfa analizi kayıtlı yanıtla; canlı çağrı yok


def test_photo_is_stored_as_its_largest_size_under_a_generated_name(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(provider_for(tmp_path, [passport()]))
    image = make_page_image_bytes(passport())  # type: ignore[arg-type]
    bot.telegram.files["foto1"] = image

    bot.feed(photo_update(1, LISTED_ID, "foto1"))

    (upload,) = all_uploads(session_factory)
    (stored,) = upload.files
    assert (stored.original_name, stored.mime) == ("foto_u-foto1.jpg", "image/jpeg")
    assert bot.layout is not None
    assert bot.layout.resolve(stored.stored_path).read_bytes() == image
    getfile_ids = [p["file_id"] for name, p in bot.telegram.calls if name == "getFile"]
    assert getfile_ids == ["foto1"]  # küçük boyut değil, en büyüğü indirildi
    assert upload.status == UploadStatus.DONE.value


def test_document_without_a_name_gets_one_from_its_identity_and_mime(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    bot = make_intake_bot()
    bot.telegram.files["f9"] = make_docx_bytes()

    bot.feed(
        document_update(
            1,
            LISTED_ID,
            "f9",
            None,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    )

    (upload,) = all_uploads(session_factory)
    (name,) = file_names(session_factory, upload.id)
    assert name.startswith("belge_u-f9.")  # uzantı MIME türünden


def test_the_handler_returns_before_the_pipeline_finishes(
    make_intake_bot: Callable[..., IntakeBot], listed: None
) -> None:
    """İşleyici bekletmez: sıradaki güncellemeler (ör. `/yardim`) belge işlenirken de yanıtlanır."""
    bot = make_intake_bot()
    bot.telegram.files["f1"] = make_docx_bytes()

    bot.feed(document_update(1, LISTED_ID, "f1", "ozgecmis.docx"), message_update(2, LISTED_ID))

    texts = bot.telegram.sent_texts()
    assert texts[0].startswith("Merhaba")  # yardım, belgenin alındı iletisinden önce gitti
    assert len(texts) == 1 + 2  # yardım + "alındı" + "sağlayıcı kurulamadı" özeti


# --- 12.2.3: sonuç özeti ------------------------------------------------------------------------


def test_summary_lists_the_ready_document_without_names_or_numbers(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(provider_for(tmp_path, [passport()]))
    bot.telegram.files["f1"] = passport_pdf()

    bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))

    (upload,) = all_uploads(session_factory)
    with session_factory() as session:
        (document,) = session.scalars(select(Document)).all()
        type_name = document.document_type.name
        employee_id = document.employee_id
    received, summary = bot.telegram.sent_texts()
    assert received == "1 dosya alındı. İşleniyor; bitince sonucu yazacağım."
    assert f"Parti {upload.id}: tamamlandı." in summary
    assert "Hazır: 1 belge." in summary
    assert f"• {type_name} — {employee_id}" in summary
    assert "Kuyruğa düşen" not in summary
    # CONVENTIONS §6: kimlik alanları iletiye girmez.
    for personal in ("Ornekova", "ORNEKOVA", DOCUMENT_NUMBER, "Ekaterina"):
        assert personal not in summary
    chats = {p["chat_id"] for name, p in bot.telegram.calls if name == "sendMessage"}
    assert chats == {LISTED_ID}  # yalnız gönderene, özel sohbete


def test_queued_items_are_summarised_with_their_kind_and_reason(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(idle_provider(tmp_path))  # Word eki analiz edilmez
    bot.telegram.files["w1"] = make_docx_bytes()

    bot.feed(document_update(1, LISTED_ID, "w1", "ozgecmis.docx"))

    (upload,) = all_uploads(session_factory)
    with session_factory() as session:
        (queued,) = session.scalars(select(QueueItem)).all()
        assert queued.kind == "unresolved"
        reason = " ".join(queued.reason.split())
    _, summary = bot.telegram.sent_texts()
    assert f"Parti {upload.id}: tamamlandı." in summary
    assert "Kuyruğa düşen: 1 öğe." in summary
    assert f"• Unresolved: {reason[:60]}" in summary
    assert "Hazır:" not in summary


def test_a_long_queue_is_cut_off_with_the_remaining_count(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(idle_provider(tmp_path))
    updates = []
    for index in range(12):
        bot.telegram.files[f"w{index}"] = make_docx_bytes() + bytes([index])
        updates.append(
            document_update(
                index + 1, LISTED_ID, f"w{index}", f"cv{index}.docx", media_group_id="g"
            )
        )

    bot.feed(*updates)

    _, summary = bot.telegram.sent_texts()
    assert "Kuyruğa düşen: 12 öğe." in summary
    assert summary.count("• Unresolved:") == 10
    assert "… ve 2 öğe daha." in summary
    assert len(summary) <= 4000


def test_a_summary_only_counts_its_own_batch(
    make_intake_bot: Callable[..., IntakeBot], listed: None, tmp_path: Path
) -> None:
    """Önceki partinin kuyruk öğesi ve belgesi sonraki partinin özetine sızmaz."""
    bot = make_intake_bot(provider_for(tmp_path, [passport()]))
    bot.telegram.files["w"] = make_docx_bytes()
    bot.telegram.files["p"] = passport_pdf()

    bot.feed(
        document_update(1, LISTED_ID, "w", "ozgecmis.docx"),
        document_update(2, LISTED_ID, "p", "pasaport.pdf"),
        pause=0.3,
    )

    _, queue_summary, _, ready_summary = bot.telegram.sent_texts()
    assert "Kuyruğa düşen: 1 öğe." in queue_summary and "Hazır:" not in queue_summary
    assert "Hazır: 1 belge." in ready_summary and "Kuyruğa düşen" not in ready_summary


def test_many_ready_documents_are_cut_off_with_the_remaining_count(
    make_intake_bot: Callable[..., IntakeBot],
    monkeypatch: pytest.MonkeyPatch,
    listed: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(handlers, "_MAX_LISTED", 1)
    other = passport_page(
        PERSON_SIDOROV, document_number="00 0000002", expiry_date=date(2031, 1, 1)
    )
    bot = make_intake_bot(provider_for(tmp_path, [passport()], [other]))
    bot.telegram.files["a"] = passport_pdf()
    bot.telegram.files["b"] = make_document_pdf_bytes([other])  # type: ignore[list-item]

    bot.feed(
        document_update(1, LISTED_ID, "a", "a.pdf", media_group_id="g"),
        document_update(2, LISTED_ID, "b", "b.pdf", media_group_id="g"),
    )

    summary = bot.telegram.sent_texts()[-1]
    assert "Hazır: 2 belge." in summary
    assert summary.count("• ") == 1
    assert "… ve 1 öğe daha." in summary


def test_a_repeated_file_is_reported_as_a_duplicate(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(provider_for(tmp_path, [passport()], []))
    bot.telegram.files["f1"] = passport_pdf()

    bot.feed(
        document_update(1, LISTED_ID, "f1", "pasaport.pdf"),
        document_update(2, LISTED_ID, "f1", "pasaport-yeniden.pdf"),
        pause=0.3,
    )

    first, second = all_uploads(session_factory)
    assert first.files[0].is_duplicate_of is None
    assert second.files[0].is_duplicate_of == first.files[0].id  # web ile aynı tekrar tespiti
    summary = bot.telegram.sent_texts()[-1]
    assert "daha önce yüklenmişti" in summary
    # Özet yalnız kendi partisinin çıktısını sayar: ilk partinin belgesi buraya sızmaz.
    assert "Hazır:" not in summary


def test_partial_batch_is_reported_as_such(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    """Sözleşmeye uymayan yanıt sayfayı analiz edilemez yapar (03.7.2): parti kısmen biter."""
    unusable = RecordingProvider.from_directory(write_recordings(tmp_path / "kayit", [{}]))
    bot = make_intake_bot(unusable)
    bot.telegram.files["f1"] = passport_pdf()

    bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))

    (upload,) = all_uploads(session_factory)
    assert upload.status == UploadStatus.PARTIAL.value
    assert "kısmen tamamlandı" in bot.telegram.sent_texts()[-1]


def test_a_pipeline_that_stops_is_reported_and_the_file_stays_stored(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    """Sağlayıcı yanıtları bitince analiz durur (09.2.3): parti `failed`, dosya Inbox'ta."""
    bot = make_intake_bot(provider_for(tmp_path, [passport()]))
    pdf = make_document_pdf_bytes([passport(), passport()])  # type: ignore[list-item]
    bot.telegram.files["f1"] = pdf

    bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))

    (upload,) = all_uploads(session_factory)
    assert upload.status == UploadStatus.FAILED.value
    assert bot.layout is not None
    assert bot.layout.resolve(upload.files[0].stored_path).read_bytes() == pdf
    assert bot.telegram.sent_texts()[-1] == (
        f"Parti {upload.id}: işlenemedi.\nDosyalar saklandı; ayrıntı için panelde partiye bakın."
    )


def test_summary_of_a_failed_batch_without_a_plan(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(Upload(id="u_20260101_001", channel="telegram", status="failed"))
        session.commit()
        failed = ProcessedUpload(UploadStatus.FAILED, None, failed_stage=UploadStatus.RENDERING)

        text = build_summary(session, "u_20260101_001", failed)

    assert text == (
        "Parti u_20260101_001: işlenemedi.\nDosyalar saklandı; ayrıntı için panelde partiye bakın."
    )


def test_summary_without_outputs_says_so(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    """Boş sayfa atlanır (S8): ne belge ne kuyruk çıkar."""
    bot = make_intake_bot(idle_provider(tmp_path))
    bot.telegram.files["b1"] = make_document_pdf_bytes([blank_page()])

    bot.feed(document_update(1, LISTED_ID, "b1", "bos.pdf"))

    assert NO_OUTPUT_TEXT in bot.telegram.sent_texts()[-1]


# --- 12.2.2: çoklu mesaj grubu ------------------------------------------------------------------


def test_files_of_one_album_form_a_single_upload_and_one_summary(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(provider_for(tmp_path, [passport()], []))
    bot.telegram.files["a"] = passport_pdf()
    bot.telegram.files["b"] = make_docx_bytes()

    bot.feed(
        # Telegram sırayı garanti etmez; dosyalar mesaj numarasıyla sıralanır.
        document_update(2, LISTED_ID, "b", "ozgecmis.docx", message_id=11, media_group_id="album1"),
        document_update(1, LISTED_ID, "a", "pasaport.pdf", message_id=10, media_group_id="album1"),
    )

    (upload,) = all_uploads(session_factory)
    assert file_names(session_factory, upload.id) == ["pasaport.pdf", "ozgecmis.docx"]
    assert upload.status == UploadStatus.DONE.value
    received, summary = bot.telegram.sent_texts()
    assert received == "2 dosya alındı. İşleniyor; bitince sonucu yazacağım."
    assert "Hazır: 1 belge." in summary
    assert "Kuyruğa düşen: 1 öğe." in summary


def test_the_wait_restarts_with_every_album_file(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    """Dosyalar arası aralık bekleme süresinden kısaysa toplam süre uzasa da tek parti olur."""
    bot = make_intake_bot(idle_provider(tmp_path), group_wait=0.2)
    updates = []
    for index in range(4):
        bot.telegram.files[f"w{index}"] = make_docx_bytes() + bytes([index])
        updates.append(
            document_update(
                index + 1, LISTED_ID, f"w{index}", f"cv{index}.docx", media_group_id="g"
            )
        )

    bot.feed(*updates, pause=0.12)  # toplam ~0,36 sn > 0,2 sn, ama her aralık 0,12 sn

    (upload,) = all_uploads(session_factory)
    assert len(file_names(session_factory, upload.id)) == 4


def test_a_file_arriving_after_the_wait_starts_a_new_upload(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(idle_provider(tmp_path), group_wait=0.05)
    for name in ("a", "b"):
        bot.telegram.files[name] = make_docx_bytes() + name.encode()

    bot.feed(
        document_update(1, LISTED_ID, "a", "a.docx", media_group_id="album1"),
        document_update(2, LISTED_ID, "b", "b.docx", media_group_id="album1"),
        pause=0.4,
    )

    first, second = all_uploads(session_factory)
    assert [len(first.files), len(second.files)] == [1, 1]


def test_separate_albums_and_single_messages_are_separate_uploads(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(idle_provider(tmp_path))
    for name in ("a1", "a2", "b1", "c1", "c2"):
        bot.telegram.files[name] = make_docx_bytes() + name.encode()

    bot.feed(
        document_update(1, LISTED_ID, "a1", "a1.docx", media_group_id="A"),
        document_update(2, LISTED_ID, "b1", "b1.docx", media_group_id="B"),
        document_update(3, LISTED_ID, "a2", "a2.docx", media_group_id="A"),
        document_update(4, LISTED_ID, "c1", "c1.docx"),  # albüm değil: kendi partisi
        document_update(5, LISTED_ID, "c2", "c2.docx"),  # art arda gelse de ayrı parti
    )

    uploads = all_uploads(session_factory)
    assert sorted(len(upload.files) for upload in uploads) == [1, 1, 1, 2]


def test_album_files_with_the_same_name_get_numbered_names(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(idle_provider(tmp_path))
    for name in ("a", "b", "c"):
        bot.telegram.files[name] = make_docx_bytes() + name.encode()

    bot.feed(
        document_update(1, LISTED_ID, "a", "cv.docx", media_group_id="g"),
        document_update(2, LISTED_ID, "b", "CV.docx", media_group_id="g"),
        document_update(3, LISTED_ID, "c", "cv.docx", media_group_id="g"),
    )

    (upload,) = all_uploads(session_factory)
    assert file_names(session_factory, upload.id) == ["cv.docx", "CV-2.docx", "cv-3.docx"]


def test_photo_album_is_one_upload(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
) -> None:
    bot = make_intake_bot(provider_for(tmp_path, [passport()], [passport()]))
    bot.telegram.files["p1"] = make_page_image_bytes(passport())  # type: ignore[arg-type]
    bot.telegram.files["p2"] = make_page_image_bytes(passport(), "PNG")  # type: ignore[arg-type]

    bot.feed(
        photo_update(1, LISTED_ID, "p1", media_group_id="g"),
        photo_update(2, LISTED_ID, "p2", media_group_id="g"),
    )

    (upload,) = all_uploads(session_factory)
    assert file_names(session_factory, upload.id) == ["foto_u-p1.jpg", "foto_u-p2.jpg"]


# --- sınırlar ve hatalar ------------------------------------------------------------------------


def test_file_over_the_size_limit_opens_no_upload_and_is_not_downloaded(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    bot = make_intake_bot(max_upload_file_size_bytes=2 * 1024 * 1024)
    bot.telegram.files["big"] = b"x"

    bot.feed(document_update(1, LISTED_ID, "big", "dev.pdf", file_size=5 * 1024 * 1024))

    assert all_uploads(session_factory) == []
    assert "getFile" not in bot.telegram.methods()
    assert bot.telegram.sent_texts() == [
        "'dev.pdf' dosyası 2 MB sınırını aşıyor. Lütfen dosyayı bölüp tekrar gönderin."
    ]


def test_size_limit_is_enforced_on_the_downloaded_bytes_too(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    """Telegram boyutu bildirmeyebilir; 01.3.1 denetimi indirilen baytlara da uygulanır."""
    bot = make_intake_bot(max_upload_file_size_bytes=1000)
    bot.telegram.files["big"] = b"%PDF-" + b"x" * 5000

    bot.feed(document_update(1, LISTED_ID, "big", "dev.pdf"))  # file_size bildirilmedi

    assert all_uploads(session_factory) == []
    (text,) = bot.telegram.sent_texts()
    assert "'dev.pdf' dosyası" in text and "sınırını aşıyor" in text


def test_one_oversized_file_rejects_the_whole_album(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    bot = make_intake_bot(max_upload_file_size_bytes=1000)
    bot.telegram.files["ok"] = make_docx_bytes()[:100]
    bot.telegram.files["big"] = b"x" * 5000

    bot.feed(
        document_update(1, LISTED_ID, "ok", "kucuk.docx", media_group_id="g"),
        document_update(2, LISTED_ID, "big", "dev.docx", media_group_id="g"),
    )

    assert all_uploads(session_factory) == []  # web ile aynı: hiç parti açılmaz
    assert len(bot.telegram.sent_texts()) == 1


def test_telegram_refusing_a_big_download_is_reported_as_a_size_problem(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    bot = make_intake_bot()  # `files`'ta yok: Bot API "file is too big" der

    bot.feed(document_update(1, LISTED_ID, "yok", "dev.pdf"))

    assert all_uploads(session_factory) == []
    (text,) = bot.telegram.sent_texts()
    assert text == (
        "'dev.pdf' dosyası 20 MB sınırını aşıyor. Lütfen dosyayı bölüp tekrar gönderin."
    )


def test_a_failed_download_opens_no_upload(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = make_intake_bot()
    bot.telegram.files["f1"] = b"%PDF-"
    bot.telegram.download_errors["f1"] = "Bad Request: wrong file_id"

    with caplog.at_level(logging.INFO):
        bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))

    assert all_uploads(session_factory) == []
    assert bot.telegram.sent_texts() == [DOWNLOAD_FAILED_TEXT.format(name="pasaport.pdf")]
    assert "Wrong file_id" not in caplog.text  # hata metni loga girmez, yalnız türü
    assert "indirilemedi (BadRequest)" in caplog.text


def test_without_a_provider_the_files_are_kept_and_the_user_is_told(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    bot = make_intake_bot()  # sağlayıcı kurulamaz
    pdf = passport_pdf()
    bot.telegram.files["f1"] = pdf

    bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))

    (upload,) = all_uploads(session_factory)
    assert upload.status == UploadStatus.RECEIVED.value  # işlenmedi ama kayıp yok (K10)
    assert bot.layout is not None
    assert bot.layout.resolve(upload.files[0].stored_path).read_bytes() == pdf
    received, notice = bot.telegram.sent_texts()
    assert received.startswith("1 dosya alındı")
    assert notice == (
        f"Parti {upload.id}: 1 dosya alındı ve saklandı, ama yapay zekâ sağlayıcısı "
        "kurulamadığı için işlenmiyor. Yöneticiye bildirin."
    )


def test_an_unexpected_error_is_reported_without_leaking_its_text(
    make_intake_bot: Callable[..., IntakeBot],
    monkeypatch: pytest.MonkeyPatch,
    listed: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = make_intake_bot()
    bot.telegram.files["f1"] = b"%PDF-"

    def boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("Ekaterina Ornekova 00 0000001")

    monkeypatch.setattr(handlers, "store_upload", boom)

    with caplog.at_level(logging.INFO):
        bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))

    assert bot.telegram.sent_texts() == [FAILURE_TEXT]
    assert "RuntimeError" in caplog.text
    assert "Ornekova" not in caplog.text


def test_a_failing_notification_does_not_undo_the_processing(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bot = make_intake_bot(provider_for(tmp_path, [passport()]))
    bot.telegram.files["f1"] = passport_pdf()
    bot.telegram.fail_send = True

    with caplog.at_level(logging.INFO):
        bot.feed(document_update(1, LISTED_ID, "f1", "pasaport.pdf"))

    (upload,) = all_uploads(session_factory)
    assert upload.status == UploadStatus.DONE.value
    assert "iletisi gönderilemedi (BadRequest)" in caplog.text


# --- 12.1.2 ile birlikte: kapı belgeleri de süzer ------------------------------------------------


def test_a_user_off_the_list_cannot_send_documents(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    bot = make_intake_bot()
    bot.telegram.files["f1"] = make_docx_bytes()

    bot.feed(
        document_update(1, OTHER_ID, "f1", "ozgecmis.docx"),
        photo_update(2, OTHER_ID, "f1"),
    )

    assert all_uploads(session_factory) == []
    assert bot.telegram.methods() == []  # ne indirme ne yanıt


def test_documents_sent_in_a_group_chat_are_ignored_even_from_a_listed_user(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    bot = make_intake_bot()
    bot.telegram.files["f1"] = make_docx_bytes()

    bot.feed(document_update(1, LISTED_ID, "f1", "ozgecmis.docx", chat_type="group"))

    assert all_uploads(session_factory) == []
    assert bot.telegram.methods() == []


def test_plain_text_is_not_treated_as_a_document(
    make_intake_bot: Callable[..., IntakeBot],
    session_factory: sessionmaker[Session],
    listed: None,
) -> None:
    bot = make_intake_bot()

    bot.feed(message_update(1, LISTED_ID, "merhaba"))

    assert all_uploads(session_factory) == []
    assert bot.telegram.methods() == []


def test_a_message_without_a_file_or_a_sender_is_ignored(
    make_intake_bot: Callable[..., IntakeBot], session_factory: sessionmaker[Session]
) -> None:
    """İşleyici süzgeçle çağrılır, yine de kendi başına savunmalıdır (kapı zaten süzer)."""
    bot = make_intake_bot()
    assert bot.intake is not None
    no_file = Update.de_json(message_update(1, LISTED_ID, "merhaba"), bot.application.bot)
    no_sender = Update.de_json(
        {"update_id": 2, "message": message_update(2, None, "x")["message"]}, bot.application.bot
    )

    async def call() -> None:
        for update in (no_file, no_sender):
            await bot.intake.receive(update, None)  # type: ignore[union-attr,arg-type]
        await bot.intake.join()  # type: ignore[union-attr]

    asyncio.run(call())

    assert all_uploads(session_factory) == []
    assert telegram_file(no_file.message) is None  # type: ignore[arg-type]


# --- birim: ad sadeleştirme ve çakışma ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pasaport.pdf", "pasaport.pdf"),
        ("a/b\\c.pdf", "a_b_c.pdf"),
        ("rapor: 1?.pdf", "rapor_ 1_.pdf"),
        ("  bosluk.pdf  ", "bosluk.pdf"),
        ("..", "yedek"),
        ("", "yedek"),
        (None, "yedek"),
        ("a\x00b.pdf", "a_b.pdf"),
    ],
)
def test_file_names_are_made_safe(raw: str | None, expected: str) -> None:
    assert handlers._sanitized(raw, "yedek") == expected


def test_a_very_long_name_is_cut_but_keeps_its_extension() -> None:
    name = handlers._sanitized("x" * 400 + ".pdf", "yedek")

    assert len(name) == 255 and name.endswith(".pdf")


def test_unique_names_only_touch_the_repeats() -> None:
    def file(name: str, message_id: int) -> TelegramFile:
        return TelegramFile("id", name, None, None, message_id)

    result = unique_names([file("a.pdf", 1), file("b.pdf", 2), file("a.pdf", 3), file("A.PDF", 4)])

    assert [item.name for item in result] == ["a.pdf", "b.pdf", "a-2.pdf", "A-3.PDF"]
