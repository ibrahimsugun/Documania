"""Telegram üzerinden belge alma ve sonuç özeti (PRD 12.2.1, 12.2.2, 12.2.3; K2, K10, K13, K17).

Bota gönderilen her belge ve fotoğraf, web yüklemesiyle aynı boru hattından geçer (12.2.1):
`app.web.routers.uploads.store_upload` (boyut/sayfa sınırı, Inbox'a değişmez yazma, tekrar
tespiti) ile partiye çevrilir, sonra render → analiz → plan → uygulama adımlarından geçer. Partinin
kalıcı işçi kuyruğundaki işi (13.3.1) botun kimliğiyle alınmış olarak açılır ve bot onu hemen
kendisi işler (`app.worker.run_claimed_upload`); bot işin ortasında durursa kirası dolan işi panelin
kuyruk döngüsü kaldığı aşamadan sürdürür (o partinin özeti gönderilmez). Yalnız kanal
(`uploads.channel = telegram`) ve yükleyen (beyaz listedeki kullanıcının panel kullanıcı adı)
farklıdır. Bot dosyayı olduğu gibi indirir ve saklar; içeriğe
hiçbir işlem yapmaz (K11, K17). Fotoğraf olarak gönderilen görüntüyü Telegram kendisi yeniden
kodlayıp küçültür — bunun önüne geçilemez; belge olarak (dosya eki) gönderilen bayt bayt korunur.

**Çoklu mesaj grubu (12.2.2).** Albümdeki her dosya Telegram'dan ayrı mesaj olarak gelir; hepsi
aynı `media_group_id`'yi taşır. Bu mesajlar `(sohbet, media_group_id)` anahtarıyla biriktirilir ve
`group_wait` saniye boyunca yeni dosya gelmezse tek parti olarak açılır. Gruba ait olmayan mesaj
beklemeden kendi partisini açar. Bekleme sırasında işleyici hemen döner (sıradaki güncellemeleri
tutmaz); indirme, kayıt ve işleme arka planda çalışır. Bekleme süresinden sonra gelen geç bir
albüm dosyası yeni bir parti olur.

**Sonuç özeti (12.2.3).** Parti kaydedilince kısa bir "alındı" iletisi, işleme bitince tek bir
özet gider: partinin durumu, Hazir'a giden belgeler (tür ve çalışan numarası — ad-soyad ve belge
numarası yazılmaz) ve kuyruğa düşen öğeler (kuyruk türü ve gerekçe). Sonuç yalnız gönderene, özel
sohbete gider (beyaz liste kapısı `bot.GATE_GROUP`). Yapay zekâ sağlayıcısı kurulamıyorsa dosya
yine Inbox'ta güvendedir; kullanıcıya işlenmediği söylenir.

**Sınırlar.** Telegram Bot API bota 20 MB'tan büyük dosya indirtmez; `MAX_UPLOAD_FILE_SIZE_BYTES`
sınırını aşan ya da indirilemeyen dosya varsa parti hiç açılmaz (web ile aynı kural, 01.3.1) ve
kullanıcıya dosyayı bölmesi söylenir. Albümde aynı ada sahip birden çok dosya varsa (aynı partide
aynı ad olmaz) ikincisi `-2`, üçüncüsü `-3` eki alır; adsız fotoğraf `foto_<kimlik>.jpg` adını alır.
Mesajın açıklama (`caption`) metni kullanılmaz: çalışan bağlamı bu görevin kapsamında değil.

**Dil (12.1.6).** İletiler gönderenin arayüz dilindedir (`app.telegram.bot.WhitelistGate`'in
yazdığı dil; arka plan işi onu oluşturulduğu anki bağlamdan alır). Belge türü adı, çalışan numarası
ve kuyruk gerekçesi veridir, çevrilmez.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from telegram import Bot, Message, Update
from telegram.error import TelegramError
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from app.ai.provider import AnalysisProvider, ProviderConfigError, create_provider
from app.config import Settings
from app.db.models import (
    Document,
    QueueItem,
    TelegramUser,
    UploadFile,
    UploadStatus,
)
from app.i18n import N_, gettext, ngettext, translate
from app.pipeline.orchestrate import ProcessedUpload
from app.storage import DataLayout
from app.storage.filetype import extension_for_mime, mime_for_name
from app.web.routers.uploads import IncomingFile, store_upload
from app.worker import Claim, new_claim_token, release_claim, run_claimed_upload

logger = logging.getLogger(__name__)

UPLOAD_CHANNEL = "telegram"
# Albümün son dosyasından sonra yeni dosya beklenen süre. Telegram albüm mesajlarını birkaç yüz
# milisaniye aralıkla gönderir; iki saniye yavaş bağlantıda da albümü böler nadir.
GROUP_WAIT_SECONDS = 2.0

# Dosya adında dosya sistemlerinin reddettiği karakterler (`/`, `\` yol ayracı; Windows'un
# yasakları veri dizini oraya konursa yazmayı düşürmesin diye).
_FORBIDDEN_NAME_CHARS = frozenset('/\\:*?"<>|')
_MAX_NAME_LENGTH = 255  # `upload_files.original_name`
_MAX_LISTED = 10  # özette tek tek sayılan belge/kuyruk öğesi
_MAX_REASON_LENGTH = 160
_MAX_MESSAGE_LENGTH = 4000  # Telegram sınırı 4096

# Metinler kaynak dilde (Türkçe msgid) tanımlıdır, gönderilirken `gettext` ile çevrilir (12.1.6).
STATUS_LABELS: dict[UploadStatus, str] = {
    UploadStatus.DONE: N_("tamamlandı"),
    UploadStatus.PARTIAL: N_("kısmen tamamlandı — bazı sayfalar analiz edilemedi"),
    UploadStatus.FAILED: N_("işlenemedi"),
}
# Panelle aynı Türkçe adlar (app.web.routers.upload_page.QUEUE_LABELS); kuyruk klasörü İngilizce.
QUEUE_LABELS = {
    "unknown": N_("Tür bilinmiyor"),
    "unreadable": N_("Okunamadı"),
    "unresolved": N_("Sahibi belirsiz"),
}

TOO_LARGE_TEXT = N_(
    "'{name}' dosyası {limit} MB sınırını aşıyor. Lütfen dosyayı bölüp tekrar gönderin."
)
DOWNLOAD_FAILED_TEXT = N_("'{name}' dosyası Telegram'dan indirilemedi. Lütfen tekrar gönderin.")
FAILURE_TEXT = N_("Dosyalar işlenirken beklenmeyen bir hata oluştu. Lütfen tekrar deneyin.")
HANDED_OVER_TEXT = N_(
    "Parti {upload_id}: işleme başka bir işleyiciye geçti; sonucu panelde görebilirsiniz."
)
NO_OUTPUT_TEXT = N_("Yeni belge çıkmadı.")


def received_text(count: int) -> str:
    """Parti kaydedilince giden "alındı" iletisi."""
    return ngettext(
        "{count} dosya alındı. İşleniyor; bitince sonucu yazacağım.",
        "{count} dosya alındı. İşleniyor; bitince sonucu yazacağım.",
        count,
    ).format(count=count)


def unprocessed_text(upload_id: str, count: int) -> str:
    """Sağlayıcı kurulamadığında giden ileti: dosyalar saklandı, işlenmiyor."""
    return ngettext(
        "Parti {upload_id}: {count} dosya alındı ve saklandı, ama yapay zekâ sağlayıcısı "
        "kurulamadığı için işlenmiyor. Yöneticiye bildirin.",
        "Parti {upload_id}: {count} dosya alındı ve saklandı, ama yapay zekâ sağlayıcısı "
        "kurulamadığı için işlenmiyor. Yöneticiye bildirin.",
        count,
    ).format(upload_id=upload_id, count=count)


@dataclass(frozen=True, slots=True)
class TelegramFile:
    """Mesajdan okunan dosya: indirilecek kimlik ve partiye girecek (sadeleşmiş) ad."""

    file_id: str
    name: str
    mime: str | None
    size: int | None
    message_id: int


@dataclass(slots=True)
class _Group:
    """Albüm için biriken dosyalar; `last_seen` en son dosyanın olay döngüsü saati."""

    chat_id: int
    telegram_id: int
    last_seen: float
    files: list[TelegramFile] = field(default_factory=list)


class _Refused(Exception):
    """Parti açılmadı; ileti kullanıcıya olduğu gibi gider."""


def _sanitized(name: str | None, fallback: str) -> str:
    cleaned = "".join(
        "_" if char in _FORBIDDEN_NAME_CHARS or ord(char) < 32 else char for char in (name or "")
    ).strip()
    if cleaned in {"", ".", ".."}:
        return fallback
    if len(cleaned) > _MAX_NAME_LENGTH:
        suffix = PurePosixPath(cleaned).suffix
        suffix = suffix if len(suffix) < _MAX_NAME_LENGTH // 2 else ""
        cleaned = cleaned[: _MAX_NAME_LENGTH - len(suffix)] + suffix
    return cleaned


def telegram_file(message: Message) -> TelegramFile | None:
    """Mesajdaki belgeyi (dosya eki) ya da fotoğrafı okur; ikisi de yoksa `None`."""
    if message.document is not None:
        document = message.document
        mime = document.mime_type or mime_for_name(document.file_name)
        extension = extension_for_mime(mime)
        return TelegramFile(
            file_id=document.file_id,
            name=_sanitized(document.file_name, f"belge_{document.file_unique_id}{extension}"),
            mime=mime,
            size=document.file_size,
            message_id=message.message_id,
        )
    if message.photo:
        photo = message.photo[-1]  # Telegram boyutları küçükten büyüğe sıralar
        return TelegramFile(
            file_id=photo.file_id,
            name=f"foto_{photo.file_unique_id}.jpg",
            mime="image/jpeg",
            size=photo.file_size,
            message_id=message.message_id,
        )
    return None


def unique_names(files: Sequence[TelegramFile]) -> list[TelegramFile]:
    """Aynı partide aynı ad olmaz: tekrar eden ad `-2`, `-3` eki alır (büyük/küçük harf farkı
    aynı ad sayılır — veri dizini büyük/küçük harfe duyarsız olabilir)."""
    used: set[str] = set()
    result: list[TelegramFile] = []
    for file in files:
        name = file.name
        if name.casefold() in used:
            path = PurePosixPath(name)
            counter = 2
            while (name := f"{path.stem}-{counter}{path.suffix}").casefold() in used:
                counter += 1
        used.add(name.casefold())
        result.append(replace(file, name=name))
    return result


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_summary(session: Session, upload_id: str, processed: ProcessedUpload) -> str:
    """İşlenmiş partinin kısa özeti (12.2.3): durum, Hazir'a giden belgeler, kuyruğa düşenler.

    Yalnız partinin güncel planının çıktıları sayılır. Ad-soyad ve belge numarası yazılmaz."""
    lines = [
        gettext("Parti {upload_id}: {status}.").format(
            upload_id=upload_id, status=gettext(STATUS_LABELS[processed.status])
        )
    ]
    if processed.plan is not None:
        lines.extend(_output_lines(session, upload_id, processed.plan.id))
    duplicates = session.scalar(
        select(func.count()).where(
            UploadFile.upload_id == upload_id, UploadFile.is_duplicate_of.is_not(None)
        )
    )
    if duplicates:
        lines.append(
            ngettext(
                "{count} dosya daha önce yüklenmişti (tekrar), işlenmedi.",
                "{count} dosya daha önce yüklenmişti (tekrar), işlenmedi.",
                duplicates,
            ).format(count=duplicates)
        )
    if processed.status is UploadStatus.FAILED:
        lines.append(gettext("Dosyalar saklandı; ayrıntı için panelde partiye bakın."))
    return _shorten_message("\n".join(lines))


def _output_lines(session: Session, upload_id: str, plan_id: int) -> list[str]:
    # Yeni işlenmiş partinin tek plan sürümü vardır (yeniden analiz K18'in işidir): planın
    # belgeleri hep `active`, kuyruk öğeleri hep bu partinindir.
    documents = list(
        session.scalars(select(Document).where(Document.plan_id == plan_id).order_by(Document.id))
    )
    queued = list(
        session.scalars(
            select(QueueItem).where(QueueItem.upload_id == upload_id).order_by(QueueItem.id)
        )
    )
    if not documents and not queued:
        return [gettext(NO_OUTPUT_TEXT)]
    lines: list[str] = []
    if documents:
        lines.append(
            ngettext("Hazır: {count} belge.", "Hazır: {count} belge.", len(documents)).format(
                count=len(documents)
            )
        )
        lines.extend(
            f"• {document.document_type.name} — {document.employee_id}"
            for document in documents[:_MAX_LISTED]
        )
        lines.extend(_more(len(documents)))
    if queued:
        lines.append(
            ngettext(
                "Kuyruğa düşen: {count} öğe.", "Kuyruğa düşen: {count} öğe.", len(queued)
            ).format(count=len(queued))
        )
        lines.extend(
            f"• {gettext(QUEUE_LABELS[item.kind]) if item.kind in QUEUE_LABELS else item.kind}: "
            f"{_shorten(item.reason, _MAX_REASON_LENGTH)}"
            for item in queued[:_MAX_LISTED]
        )
        lines.extend(_more(len(queued)))
    return lines


def _more(total: int) -> Iterable[str]:
    if total > _MAX_LISTED:
        rest = total - _MAX_LISTED
        yield ngettext("… ve {count} öğe daha.", "… ve {count} öğe daha.", rest).format(count=rest)


def _shorten_message(text: str) -> str:
    return text if len(text) <= _MAX_MESSAGE_LENGTH else text[: _MAX_MESSAGE_LENGTH - 1] + "…"


ProviderFactory = Callable[[Settings], AnalysisProvider]


class DocumentIntake:
    """Belge ve fotoğraf mesajlarını partiye çevirir ve sonucu bildirir (modül açıklaması)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        layout: DataLayout,
        settings: Settings,
        *,
        provider_factory: ProviderFactory = create_provider,
        group_wait: float = GROUP_WAIT_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._layout = layout
        self._settings = settings
        self._provider_factory = provider_factory
        self._group_wait = group_wait
        self._groups: dict[tuple[int, str], _Group] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def register(self, application: Application, *, group: int) -> None:
        """Belge/fotoğraf işleyicisini ekler. `group` beyaz liste kapısından büyük olmalıdır."""
        application.add_handler(
            MessageHandler(filters.Document.ALL | filters.PHOTO, self.receive), group=group
        )

    async def receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Bir mesajı partiye katar: albüm dosyası biriktirilir, tekil dosya hemen işlenir.

        Hızlı döner; asıl iş arka plandadır (sıradaki güncellemeler beklemez)."""
        message, user = update.effective_message, update.effective_user
        incoming = telegram_file(message) if message is not None else None
        if message is None or user is None or incoming is None:
            return
        if message.media_group_id is None:
            self._spawn(self._handle(context.bot, message.chat_id, user.id, [incoming]))
            return
        key = (message.chat_id, message.media_group_id)
        loop = asyncio.get_running_loop()
        group = self._groups.get(key)
        if group is None:
            group = self._groups[key] = _Group(message.chat_id, user.id, loop.time())
            self._spawn(self._close_group(context.bot, key))
        group.files.append(incoming)
        group.last_seen = loop.time()

    async def join(self) -> None:
        """Süren bütün arka plan işlerinin bitmesini bekler (kapanış ve testler için)."""
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coroutine)
        self._tasks.add(task)  # olay döngüsü görevi zayıf tutar; iş bitene kadar biz tutarız
        task.add_done_callback(self._tasks.discard)

    async def _close_group(self, bot: Bot, key: tuple[int, str]) -> None:
        """Albümde `group_wait` saniye yeni dosya gelmeyince onu tek parti olarak işler."""
        loop = asyncio.get_running_loop()
        group = self._groups[key]
        while (remaining := group.last_seen + self._group_wait - loop.time()) > 0:
            await asyncio.sleep(remaining)
        del self._groups[key]
        files = sorted(group.files, key=lambda file: file.message_id)
        await self._handle(bot, group.chat_id, group.telegram_id, files)

    async def _handle(
        self, bot: Bot, chat_id: int, telegram_id: int, files: Sequence[TelegramFile]
    ) -> None:
        try:
            text = await self._process(bot, chat_id, telegram_id, unique_names(files))
        except _Refused as refusal:
            text = str(refusal)
        except Exception as exc:
            # İleti kimlik/içerik taşıyabilir (SQL parametresi, dosya yolu); yalnız türü yazılır.
            logger.error("Telegram belge partisi işlenemedi (%s)", type(exc).__name__)
            text = gettext(FAILURE_TEXT)
        await _send(bot, chat_id, text)

    async def _process(
        self, bot: Bot, chat_id: int, telegram_id: int, files: Sequence[TelegramFile]
    ) -> str:
        incoming = await self._download(bot, files)
        token = new_claim_token()
        try:
            upload_id = await asyncio.to_thread(self._store, telegram_id, incoming, token)
        except HTTPException as exc:  # sınır aşımı gibi kullanıcıya söylenecek ret (01.3.1)
            raise _Refused(translate(exc.detail)) from None
        await _send(bot, chat_id, received_text(len(incoming)))
        return await asyncio.to_thread(self._run_pipeline, Claim(upload_id, token), len(incoming))

    async def _download(self, bot: Bot, files: Sequence[TelegramFile]) -> list[IncomingFile]:
        limit = self._settings.max_upload_file_size_bytes
        for file in files:
            if file.size is not None and file.size > limit:
                raise _Refused(_too_large(file.name, limit))
        incoming: list[IncomingFile] = []
        for file in files:
            try:
                remote = await bot.get_file(file.file_id)
                content = bytes(await remote.download_as_bytearray())
            except TelegramError as exc:
                # Bot API 20 MB'tan büyük dosyayı vermez ("File is too big").
                if "too big" in str(exc).lower():
                    raise _Refused(_too_large(file.name, limit)) from None
                logger.error("Telegram dosyası indirilemedi (%s)", type(exc).__name__)
                raise _Refused(gettext(DOWNLOAD_FAILED_TEXT).format(name=file.name)) from None
            incoming.append(IncomingFile(file.name, content, file.mime))
        return incoming

    def _store(self, telegram_id: int, files: list[IncomingFile], token: str) -> str:
        with self._session_factory() as session:
            row = session.get(TelegramUser, telegram_id)
            return store_upload(
                session,
                self._layout,
                self._settings,
                files,
                channel=UPLOAD_CHANNEL,
                uploaded_by=row.user.username if row is not None else None,
                claimed_by=token,  # 13.3.1: iş bota alınmış açılır, kuyruk döngüsü onu almaz
            )

    def _run_pipeline(self, claim: Claim, file_count: int) -> str:
        """Partiyi web ile aynı adımlardan geçirir ve özet metnini döner (iş parçacığında)."""
        try:
            provider = self._provider_factory(self._settings)
        except ProviderConfigError as exc:
            logger.error(
                "Telegram partisi işlenemedi: sağlayıcı kurulamadı (%s)", type(exc).__name__
            )
            # İş kuyruğa geri döner: sağlayıcısı olan bir işleyici partiyi sonra işler (13.3.1).
            with self._session_factory() as session:
                release_claim(session, claim)
                session.commit()
            return unprocessed_text(claim.upload_id, file_count)
        processed = run_claimed_upload(
            self._session_factory, self._layout, claim, settings=self._settings, provider=provider
        )
        if processed is None:  # iş bu arada başka bir işleyiciye geçti
            return gettext(HANDED_OVER_TEXT).format(upload_id=claim.upload_id)
        with self._session_factory() as session:
            return build_summary(session, claim.upload_id, processed)


def _too_large(name: str, limit: int) -> str:
    return gettext(TOO_LARGE_TEXT).format(name=name, limit=f"{limit / (1024 * 1024):.0f}")


async def _send(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except TelegramError as exc:
        # Bildirim gitmese de parti işlenmiştir; metin loga yazılmaz (kimlik/içerik olabilir).
        logger.error("Telegram iletisi gönderilemedi (%s)", type(exc).__name__)
