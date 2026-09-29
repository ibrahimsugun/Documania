"""Doğal dil belge istekleri (PRD 12.3.1, 12.3.2, 12.3.3; K13, K16, K17).

İK bota "Ahmet Çakar'ın ehliyetini göster" yazar. Metin yapay zekâya **bir kez** verilir ve tek bir
araç çağrısına çevrilir (`app.ai.document_query.DocumentQuery`): `find_documents(kişi, belge türü)`
ya da `other`. Yapay zekâ veritabanını görmez; isteğe yalnız mesaj ve katalogdaki tür adları girer
(başka çalışanın verisi sağlayıcıya gitmez, CONVENTIONS §6). Aracı sistem deterministik yürütür:

1. **Kişi** (`find_employees`): ifade çalışan numarasına (`E0001`) ve ad kelimelerine ayrılır. Ad,
   kişi eşleştirmesinin anahtarına indirilir (`normalize_name`: harf büyüklüğü, aksan, Türkçe harf
   ve Kiril/Latin farkı yok) ve **tam kelime** olarak aranır: çalışanın ad yazımlarından biri
   (kayıttaki ad-soyad, diğer isimlerle birlikte, orijinal yazım ya da bir alias) aranan her
   kelimeyi taşımalıdır — "Ali" "Alican"ı bulmaz, "Çakar" her Çakar'ı bulur. Numara yazılmışsa
   yalnız o çalışandır; ad da yazılmışsa ona uymalıdır, uymazsa sonuç yoktur. Pasif çalışan
   (10.5.7) da bulunur ve belgeleri gönderilir; adı yanıtta "(pasif)" ekiyle görünür.
2. **Belgeler** (`find_documents`): çalışanın **etkin** belgeleri — eski sürüm (K18) ve arşivlenmiş
   (K16) belge önerilmez —, tür verilmişse yalnız o türlerden, yeniden eskiye.
3. **Belirsizlik** (12.3.2): birden çok çalışan uyarsa önce çalışan, çalışanın birden çok belgesi
   uyarsa belge sorulur (satır içi düğmeler, en çok `MAX_OPTIONS`); tek sonuç doğrudan gönderilir.
   Tahmin edilmez: kişisiz, çok kişili ya da katalogda karşılığı olmayan türdeki istek için
   kullanıcıya ne eksik olduğu söylenir ve hiçbir belge gönderilmez.
4. **Gönderim ve erişim kaydı** (12.3.3): belge dosyası olduğu gibi — bayt bayt, belge olarak (K10,
   K17) — gönderilir. Göndermeden **önce** `access_log`'a satır yazılır ve commit edilir: kullanıcı
   beyaz listedeki Telegram hesabının bağlı olduğu panel kullanıcısı, eylem `download`, kanal
   `telegram`. Kayıt yazılamazsa belge gitmez; gönderim sonradan başarısız olursa kayıt kalır (web
   ile aynı sıra, `app.web.access`).

**Seçim belleği.** Soru ile yanıtın bağı bot sürecinin belleğindedir (`ChoiceStore`): her soru
rastgele bir belirteç alır, düğmeler `sec:<belirteç>:<sıra>` taşır. Seçim tek kullanımlıktır, yalnız
sorulan sohbetten ve kullanıcıdan gelir, `CHOICE_TTL_SECONDS` sonra ya da aynı sohbette yeni soru
sorulunca geçersizdir; bot yeniden başlarsa eski düğmeler "geçersiz" yanıtı alır.

İşleyiciler hızlı döner; yapay zekâ çağrısı, arama ve gönderim arka planda çalışır (belge alma gibi,
`app.telegram.handlers`). Veritabanı oturumu yapay zekâ çağrısı sürerken açık tutulmaz (SQLite yazma
kilidi, `app.db.session`). Mesaj metni, kişi adı ve belge numarası loga yazılmaz (CONVENTIONS §6);
yanıt yalnız isteyene, özel sohbete gider (beyaz liste kapısı `bot.GATE_GROUP`).
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Coroutine, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from telegram import (
    Bot,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.ai.document_query import DocumentQuery, DocumentQueryError, QueryIntent
from app.ai.prompts import load_document_query_instructions
from app.ai.provider import (
    DocumentQueryRequest,
    ProviderConfigError,
    ProviderError,
    ProviderFactory,
    create_provider,
)
from app.config import Settings
from app.db.models import (
    AccessAction,
    AccessChannel,
    Document,
    DocumentStatus,
    Employee,
    EmployeeAlias,
    KnownDocumentType,
    TelegramUser,
)
from app.matching.names import EmptyNameError, normalize_name
from app.matching.status import status_suffix
from app.storage import DataLayout
from app.web.access import record_access

logger = logging.getLogger(__name__)

MAX_REQUEST_LENGTH = 500  # karakter; daha uzun mesaj yapay zekâya gönderilmez
MAX_OPTIONS = 10  # seçim sorusundaki en çok düğme
CHOICE_TTL_SECONDS = 10 * 60
MAX_PENDING_CHOICES = 1000
# Bot API'nin bota gönderttiği en büyük dosya (yerel Bot API sunucusu olmadan).
TELEGRAM_SEND_LIMIT_BYTES = 50 * 1024 * 1024

CALLBACK_PREFIX = "sec"
CALLBACK_PATTERN = re.compile(rf"^{CALLBACK_PREFIX}:([A-Za-z0-9_-]{{8,32}}):(\d{{1,2}})$")
# Çalışan numarası (K8, `format_employee_number`): `E` ve en az dört hane, kelimenin parçası değil;
# kesme işaretiyle gelen Türkçe ek ("E0001'in") numaraya aittir, ada karışmaz.
_EMPLOYEE_NUMBER = re.compile(r"(?<!\w)([Ee]\d{4,})(?:['’]\w+)?(?!\w)")
_MAX_BUTTON_LENGTH = 60
_MAX_MESSAGE_LENGTH = 4000  # Telegram sınırı 4096

NOT_A_REQUEST_TEXT = (
    "Bu mesajı bir belge isteği olarak anlayamadım. Bir çalışanın belgesini istemek için kimin "
    "hangi belgesini istediğinizi yazın, örneğin: “Ahmet Çakar'ın ehliyetini göster”. Bot belge "
    "içeriğini değiştirmez; taşıma ve arşivleme panelden yapılır. Yardım: /yardim"
)
NO_PERSON_TEXT = "Kimin belgesini istediğinizi yazın: ad-soyad ya da çalışan numarası (ör. E0001)."
MANY_PEOPLE_TEXT = "Her istekte tek bir çalışanın belgesini isteyin."
UNKNOWN_KIND_TEXT = "“{kind}” katalogdaki belge türlerinden hiçbirine karşılık gelmiyor."
NO_EMPLOYEE_TEXT = "“{person}” ile eşleşen çalışan bulunamadı."
EMPLOYEE_QUESTION_TEXT = "“{person}” ile eşleşen {count} çalışan bulundu. Hangisi?"
NO_DOCUMENT_TEXT = "{employee} için {kind} bulunamadı."
DOCUMENT_QUESTION_TEXT = "{employee} için {count} {kind} bulundu. Hangisini istiyorsunuz?"
MORE_EMPLOYEES_TEXT = (
    "… ve {count} çalışan daha. Adı daha ayrıntılı ya da çalışan numarasıyla yazın."
)
MORE_DOCUMENTS_TEXT = "… ve {count} belge daha. Türü belirtin ya da panelden bakın."
STALE_CHOICE_TEXT = "Bu seçim artık geçerli değil. İsteği yeniden yazın."
TOO_LONG_TEXT = (
    "İstek çok uzun ({limit} karakterden fazla). Kimin hangi belgesini istediğinizi kısaca yazın."
)
UNAVAILABLE_TEXT = (
    "Belge isteme şu an çalışmıyor: yapay zekâ sağlayıcısı kurulamadı. Yöneticiye bildirin."
)
FAILURE_TEXT = "İsteğiniz şu an işlenemedi. Lütfen biraz sonra tekrar deneyin."
DOCUMENT_GONE_TEXT = (
    "Bu belge artık güncel değil (arşivlendi ya da yeniden analizle yenilendi). İsteği yeniden "
    "yazın."
)
FILE_MISSING_TEXT = "Belgenin dosyası bulunamadı; yöneticiye bildirin."
TOO_LARGE_TEXT = "Belge Telegram'ın gönderim sınırını ({limit_mb:.0f} MB) aşıyor; panelden indirin."
SEND_FAILED_TEXT = "Belge gönderilemedi. Lütfen tekrar deneyin."
ANY_DOCUMENT = "belge"
ANY_ACTIVE_DOCUMENT = "etkin belge"


# --- Kişi ve belge araması (12.3.1) ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PersonReference:
    """Mesajdaki kişi ifadesi: çalışan numaraları (büyük harf) ve adın eşleştirme kelimeleri."""

    numbers: tuple[str, ...]
    words: tuple[str, ...]


def parse_person(text: str) -> PersonReference:
    """İfadeyi çalışan numaralarına ve `normalize_name` kelimelerine ayırır."""
    numbers = tuple(dict.fromkeys(match.upper() for match in _EMPLOYEE_NUMBER.findall(text)))
    try:
        words = tuple(normalize_name(_EMPLOYEE_NUMBER.sub(" ", text)).split())
    except EmptyNameError:
        words = ()
    return PersonReference(numbers, words)


def _name_keys(employee: Employee, aliases: Iterable[str]) -> list[Counter[str]]:
    """Çalışanın ad yazımlarının kelime torbaları: kayıttaki ad-soyad (diğer isimlerle ve onlarsız),
    orijinal yazım ve alias'ların normalize anahtarları."""
    spellings = (
        (employee.given_names, employee.surname),
        (employee.given_names, employee.surname, employee.other_names),
        (employee.original_script_name,),
    )
    keys: list[Counter[str]] = []
    for parts in spellings:
        try:
            keys.append(Counter(normalize_name(*parts).split()))
        except EmptyNameError:
            continue
    keys.extend(Counter(alias.split()) for alias in aliases)
    return keys


def find_employees(session: Session, person: PersonReference) -> list[Employee]:
    """İfadeye uyan çalışanlar, soyad-ad sırasıyla (modül açıklaması, adım 1)."""
    if not person.numbers and not person.words:
        return []
    query = select(Employee).order_by(
        func.lower(Employee.surname), func.lower(Employee.given_names), Employee.id
    )
    alias_query = select(EmployeeAlias.employee_id, EmployeeAlias.normalized_name)
    if person.numbers:
        query = query.where(Employee.id.in_(person.numbers))
        alias_query = alias_query.where(EmployeeAlias.employee_id.in_(person.numbers))
    employees = list(session.scalars(query))
    if not person.words:
        return employees
    aliases: defaultdict[str, list[str]] = defaultdict(list)
    for employee_id, normalized in session.execute(alias_query):
        aliases[employee_id].append(normalized)
    wanted = Counter(person.words)
    return [
        employee
        for employee in employees
        if any(not wanted - key for key in _name_keys(employee, aliases[employee.id]))
    ]


def find_documents(session: Session, employee_id: str, type_slugs: Sequence[str]) -> list[Document]:
    """Çalışanın etkin belgeleri; `type_slugs` boş değilse yalnız o türlerden, yeniden eskiye."""
    query = select(Document).where(
        Document.employee_id == employee_id, Document.status == DocumentStatus.ACTIVE.value
    )
    if type_slugs:
        query = query.where(Document.type_slug.in_(type_slugs))
    return list(session.scalars(query.order_by(Document.created_at.desc(), Document.id.desc())))


def build_query_prompt(types: Iterable[KnownDocumentType], text: str) -> str:
    """Yapay zekâya giden kullanıcı metni: katalogdaki türler ve İK'nın mesajı.

    Katalog kişisel veri taşımaz (slug, ad, dosya etiketi, ülke); mesaj bölümü içindeki açı
    ayraçları benzerleriyle değişir ki metin bölümü kapatıp talimat gibi görünemesin."""
    entries = sorted(types, key=lambda entry: entry.slug)
    lines = ["<katalog>"]
    lines.extend(
        f"- {entry.slug} — {entry.name} — {entry.file_label} — {entry.country or '-'}"
        for entry in entries
    )
    if not entries:
        lines.append("(katalog boş)")
    lines += ["</katalog>", "<mesaj>", text.replace("<", "‹").replace(">", "›"), "</mesaj>"]
    return "\n".join(lines)


# --- Yanıtlar ve belirsizlik (12.3.2) ----------------------------------------------------------

ChoiceKind = Literal["employee", "document"]


@dataclass(frozen=True, slots=True)
class Lookup:
    """Seçimden sonra aramanın sürmesi için isteğin bağlamı: istenen türler, mesajdaki tür adı."""

    type_slugs: tuple[str, ...]
    kind: str | None


@dataclass(frozen=True, slots=True)
class TextReply:
    text: str


@dataclass(frozen=True, slots=True)
class Question:
    """Seçim sorusu: `options` çalışan numaraları ya da belge kimlikleri, `labels` düğmeler."""

    text: str
    kind: ChoiceKind
    options: tuple[str, ...]
    labels: tuple[str, ...]
    lookup: Lookup


@dataclass(frozen=True, slots=True)
class SendDocument:
    document_id: int


Reply = TextReply | Question | SendDocument


def resolve_query(session: Session, query: DocumentQuery) -> Reply:
    """Araç çağrısını yürütür: ne gönderileceğini ya da ne sorulacağını söyler (belge göndermez)."""
    if query.intent is QueryIntent.OTHER:
        return TextReply(NOT_A_REQUEST_TEXT)
    if not query.people:
        return TextReply(NO_PERSON_TEXT)
    if len(query.people) > 1:
        return TextReply(MANY_PEOPLE_TEXT)
    if query.document_kind is not None and not query.document_types:
        return TextReply(UNKNOWN_KIND_TEXT.format(kind=query.document_kind))
    (person,) = query.people
    lookup = Lookup(query.document_types, query.document_kind)
    employees = find_employees(session, parse_person(person))
    if not employees:
        return TextReply(NO_EMPLOYEE_TEXT.format(person=person))
    if len(employees) == 1:
        return resolve_documents(session, employees[0], lookup)
    return _employee_question(session, person, employees, lookup)


def resolve_documents(session: Session, employee: Employee, lookup: Lookup) -> Reply:
    """Kişi belli olduktan sonra: tek belge gönderilir, birden çoğu sorulur, hiç yoksa söylenir."""
    documents = find_documents(session, employee.id, lookup.type_slugs)
    if not documents:
        return TextReply(
            NO_DOCUMENT_TEXT.format(
                employee=_employee_label(employee), kind=lookup.kind or ANY_ACTIVE_DOCUMENT
            )
        )
    if len(documents) == 1:
        return SendDocument(documents[0].id)
    shown = documents[:MAX_OPTIONS]
    lines = [
        DOCUMENT_QUESTION_TEXT.format(
            employee=_employee_label(employee),
            count=len(documents),
            kind=lookup.kind or ANY_DOCUMENT,
        )
    ]
    lines.extend(
        f"{index}. {document.document_type.name} — {_file_name(document)} — "
        f"{document.created_at:%d.%m.%Y}"
        for index, document in enumerate(shown, 1)
    )
    if len(documents) > MAX_OPTIONS:
        lines.append(MORE_DOCUMENTS_TEXT.format(count=len(documents) - MAX_OPTIONS))
    return Question(
        text="\n".join(lines),
        kind="document",
        options=tuple(str(document.id) for document in shown),
        labels=tuple(
            _button_label(f"{index}. {_file_name(document)}")
            for index, document in enumerate(shown, 1)
        ),
        lookup=lookup,
    )


def _employee_question(
    session: Session, person: str, employees: Sequence[Employee], lookup: Lookup
) -> Question:
    shown = employees[:MAX_OPTIONS]
    counts = _document_counts(session, [employee.id for employee in shown], lookup.type_slugs)
    kind = lookup.kind or ANY_DOCUMENT
    lines = [EMPLOYEE_QUESTION_TEXT.format(person=person, count=len(employees))]
    for index, employee in enumerate(shown, 1):
        details = [employee.id]
        if employee.date_of_birth is not None:
            details.append(f"doğum {employee.date_of_birth:%d.%m.%Y}")
        count = counts.get(employee.id, 0)
        details.append(f"{count} {kind}" if count else f"{kind} yok")
        lines.append(f"{index}. {_listed_name(employee)} — " + " — ".join(details))
    if len(employees) > MAX_OPTIONS:
        lines.append(MORE_EMPLOYEES_TEXT.format(count=len(employees) - MAX_OPTIONS))
    return Question(
        text="\n".join(lines),
        kind="employee",
        options=tuple(employee.id for employee in shown),
        labels=tuple(
            _button_label(f"{index}. {_employee_label(employee)}")
            for index, employee in enumerate(shown, 1)
        ),
        lookup=lookup,
    )


def _document_counts(
    session: Session, employee_ids: Sequence[str], type_slugs: Sequence[str]
) -> dict[str, int]:
    query = select(Document.employee_id, func.count(Document.id)).where(
        Document.employee_id.in_(employee_ids), Document.status == DocumentStatus.ACTIVE.value
    )
    if type_slugs:
        query = query.where(Document.type_slug.in_(type_slugs))
    return {
        employee_id: count
        for employee_id, count in session.execute(query.group_by(Document.employee_id))
    }


def _full_name(employee: Employee) -> str:
    return f"{employee.given_names} {employee.surname}"


def _listed_name(employee: Employee) -> str:
    # 10.5.7: bot pasif çalışanı da bulur ve yanıtlar; adı "(pasif)" ekiyle görünür.
    return _full_name(employee) + status_suffix(employee.status)


def _employee_label(employee: Employee) -> str:
    return f"{_full_name(employee)} ({employee.id}){status_suffix(employee.status)}"


def _file_name(document: Document) -> str:
    return PurePosixPath(document.path).name


def _button_label(text: str) -> str:
    return text if len(text) <= _MAX_BUTTON_LENGTH else text[: _MAX_BUTTON_LENGTH - 1] + "…"


# --- Seçim belleği -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Choice:
    """Sorulmuş ve yanıt bekleyen seçim: hangi sohbette, kime, hangi seçeneklerle soruldu."""

    chat_id: int
    telegram_id: int
    kind: ChoiceKind
    options: tuple[str, ...]
    lookup: Lookup
    expires_at: float


class ChoiceStore:
    """Soru belirteci → seçim (modül açıklaması): tek kullanımlık, süreli, sohbet başına bir."""

    def __init__(
        self,
        ttl: float = CHOICE_TTL_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        capacity: int = MAX_PENDING_CHOICES,
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._capacity = capacity
        self._choices: dict[str, Choice] = {}

    def __len__(self) -> int:
        return len(self._choices)

    def add(self, chat_id: int, telegram_id: int, question: Question) -> str:
        """Soruyu saklar ve düğmelerin taşıyacağı belirteci döner."""
        now = self._clock()
        # Süresi geçen sorular ve bu sohbetin önceki sorusu düşer: yanıt yalnız son soruya bağlanır.
        for token in [
            token
            for token, choice in self._choices.items()
            if choice.expires_at <= now or choice.chat_id == chat_id
        ]:
            del self._choices[token]
        while len(self._choices) >= self._capacity:
            del self._choices[next(iter(self._choices))]  # en eski soru
        token = secrets.token_urlsafe(9)
        self._choices[token] = Choice(
            chat_id=chat_id,
            telegram_id=telegram_id,
            kind=question.kind,
            options=question.options,
            lookup=question.lookup,
            expires_at=now + self._ttl,
        )
        return token

    def take(self, data: str | None, chat_id: int, telegram_id: int) -> tuple[Choice, str] | None:
        """Düğme verisini çözer; seçim geçerliyse onu tüketir ve seçilen seçeneği döner.

        Geçersiz: tanınmayan veri, bilinmeyen ya da süresi geçmiş belirteç, başka sohbetten ya da
        kullanıcıdan gelen basış, olmayan sıra. Başkasının gönderdiği veri seçimi tüketmez."""
        match = CALLBACK_PATTERN.fullmatch(data or "")
        if match is None:
            return None
        token, index = match.group(1), int(match.group(2))
        choice = self._choices.get(token)
        if choice is None:
            return None
        if choice.expires_at <= self._clock():
            del self._choices[token]
            return None
        if (
            choice.chat_id != chat_id
            or choice.telegram_id != telegram_id
            or index >= len(choice.options)
        ):
            return None
        del self._choices[token]
        return choice, choice.options[index]


def _keyboard(token: str, labels: Sequence[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(label, callback_data=f"{CALLBACK_PREFIX}:{token}:{index}")]
            for index, label in enumerate(labels)
        ]
    )


# --- Gönderim ve erişim kaydı (12.3.3) ---------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Delivery:
    """Gönderilecek belge: dosyanın baytları olduğu gibi, dosya adı ve kısa açıklama."""

    content: bytes
    file_name: str
    caption: str


def _stored_file(layout: DataLayout, relative_path: str) -> Path | None:
    """Belgenin diskteki dosyası; yolu veri dizininden kaçıyorsa ya da dosya yoksa `None`."""
    try:
        path = layout.resolve(relative_path)
    except ValueError:
        return None
    return path if path.is_file() else None


class DocumentRequests:
    """Metin mesajındaki belge isteğini yanıtlar ve seçim düğmelerini işler (modül açıklaması)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        layout: DataLayout,
        settings: Settings,
        *,
        provider_factory: ProviderFactory = create_provider,
        choices: ChoiceStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._layout = layout
        self._settings = settings
        self._provider_factory = provider_factory
        self._choices = choices if choices is not None else ChoiceStore()
        self._instructions = load_document_query_instructions()
        self._tasks: set[asyncio.Task[None]] = set()

    def register(self, application: Application, *, group: int) -> None:
        """Metin ve seçim işleyicilerini ekler. `group` beyaz liste kapısından büyük olmalıdır."""
        application.add_handler(
            MessageHandler(
                filters.UpdateType.MESSAGE & filters.TEXT & ~filters.COMMAND, self.receive
            ),
            group=group,
        )
        application.add_handler(
            CallbackQueryHandler(self.choose, pattern=CALLBACK_PATTERN), group=group
        )

    async def receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Metin mesajını belge isteği olarak ele alır; hızlı döner, iş arka plandadır."""
        message, user = update.effective_message, update.effective_user
        if message is None or user is None or not message.text:
            return
        self._spawn(self._answer(context.bot, message.chat_id, user.id, message.text))

    async def choose(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Seçim düğmesine basışı sorusuna bağlar; geçerliyse arama ya da gönderim sürer."""
        query, user = update.callback_query, update.effective_user
        if query is None or user is None:
            return
        chat = query.message.chat if query.message is not None else None
        taken = self._choices.take(query.data, chat.id, user.id) if chat is not None else None
        if taken is None:
            await _answer_callback(query, STALE_CHOICE_TEXT)
            await _remove_keyboard(query)
            return
        choice, option = taken
        await _answer_callback(query, None)
        await _remove_keyboard(query)
        self._spawn(self._continue(context.bot, choice, option))

    async def join(self) -> None:
        """Süren bütün arka plan işlerinin bitmesini bekler (kapanış ve testler için)."""
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.get_running_loop().create_task(coroutine)
        self._tasks.add(task)  # olay döngüsü görevi zayıf tutar; iş bitene kadar biz tutarız
        task.add_done_callback(self._tasks.discard)

    async def _answer(self, bot: Bot, chat_id: int, telegram_id: int, text: str) -> None:
        reply: Reply
        if len(text) > MAX_REQUEST_LENGTH:
            reply = TextReply(TOO_LONG_TEXT.format(limit=MAX_REQUEST_LENGTH))
        else:
            try:
                reply = await asyncio.to_thread(self._reply_to, text)
            except Exception as exc:
                # İleti kimlik taşıyabilir (SQL parametresi); yalnız türü yazılır.
                logger.error("Telegram belge isteği yanıtlanamadı (%s)", type(exc).__name__)
                reply = TextReply(FAILURE_TEXT)
        await self._deliver(bot, chat_id, telegram_id, reply)

    def _reply_to(self, text: str) -> Reply:
        """İsteği yapay zekâya okutur ve aramayı yürütür (iş parçacığında)."""
        try:
            provider = self._provider_factory(self._settings)
        except ProviderConfigError as exc:
            logger.error("Belge isteği okunamadı: sağlayıcı kurulamadı (%s)", type(exc).__name__)
            return TextReply(UNAVAILABLE_TEXT)
        with self._session_factory() as session:
            types = session.scalars(select(KnownDocumentType)).all()
            request = DocumentQueryRequest(
                instructions=self._instructions,
                prompt=build_query_prompt(types, text),
                known_slugs=frozenset(entry.slug for entry in types),
            )
        # Oturum kapandı: sağlayıcı çağrısı sürerken yazma kilidi tutulmaz.
        try:
            query = provider.read_document_query(request)
        except (ProviderError, DocumentQueryError) as exc:
            logger.error("Belge isteği okunamadı (%s)", type(exc).__name__)
            return TextReply(FAILURE_TEXT)
        with self._session_factory() as session:
            return resolve_query(session, query)

    async def _continue(self, bot: Bot, choice: Choice, option: str) -> None:
        reply: Reply
        if choice.kind == "document":
            reply = SendDocument(int(option))
        else:
            try:
                reply = await asyncio.to_thread(self._documents_of, option, choice.lookup)
            except Exception as exc:
                logger.error("Telegram seçimi sürdürülemedi (%s)", type(exc).__name__)
                reply = TextReply(FAILURE_TEXT)
        await self._deliver(bot, choice.chat_id, choice.telegram_id, reply)

    def _documents_of(self, employee_id: str, lookup: Lookup) -> Reply:
        with self._session_factory() as session:
            employee = session.get(Employee, employee_id)
            if employee is None:
                return TextReply(STALE_CHOICE_TEXT)
            return resolve_documents(session, employee, lookup)

    async def _deliver(self, bot: Bot, chat_id: int, telegram_id: int, reply: Reply) -> None:
        if isinstance(reply, TextReply):
            await _send_text(bot, chat_id, reply.text)
        elif isinstance(reply, Question):
            token = self._choices.add(chat_id, telegram_id, reply)
            await _send_text(bot, chat_id, reply.text, reply_markup=_keyboard(token, reply.labels))
        else:
            await self._send_document(bot, chat_id, telegram_id, reply.document_id)

    async def _send_document(
        self, bot: Bot, chat_id: int, telegram_id: int, document_id: int
    ) -> None:
        outcome: Delivery | TextReply | None
        try:
            outcome = await asyncio.to_thread(self._release, telegram_id, document_id)
        except Exception as exc:
            logger.error("Telegram belgesi hazırlanamadı (%s)", type(exc).__name__)
            outcome = TextReply(FAILURE_TEXT)
        if outcome is None:
            return
        if isinstance(outcome, TextReply):
            await _send_text(bot, chat_id, outcome.text)
            return
        try:
            await bot.send_document(
                chat_id=chat_id,
                document=outcome.content,
                filename=outcome.file_name,
                caption=outcome.caption,
            )
        except TelegramError as exc:
            # Erişim kaydı gönderimden önce yazıldı ve kalır (modül açıklaması, adım 4).
            logger.error("Telegram belgesi gönderilemedi (%s)", type(exc).__name__)
            await _send_text(bot, chat_id, SEND_FAILED_TEXT)

    def _release(self, telegram_id: int, document_id: int) -> Delivery | TextReply | None:
        """Belgeyi erişim kaydını yazarak gönderime hazırlar (12.3.3; iş parçacığında).

        Kayıt dosya okunmadan ve gönderilmeden **önce** commit edilir: yazılamazsa hata yükselir
        ve belge gitmez. İsteyen artık beyaz listede değilse `None`: yanıt da gitmez (12.1.2)."""
        with self._session_factory() as session:
            account = session.get(TelegramUser, telegram_id)
            if account is None or not account.allowed:
                logger.warning("Belge gönderilmedi: istek sahibi beyaz listede değil")
                return None
            document = session.get(Document, document_id)
            if document is None or document.status != DocumentStatus.ACTIVE.value:
                return TextReply(DOCUMENT_GONE_TEXT)
            path = _stored_file(self._layout, document.path)
            if path is None:
                return TextReply(FILE_MISSING_TEXT)
            if path.stat().st_size > TELEGRAM_SEND_LIMIT_BYTES:
                return TextReply(TOO_LARGE_TEXT.format(limit_mb=TELEGRAM_SEND_LIMIT_BYTES / 2**20))
            file_name = _file_name(document)
            caption = f"{document.document_type.name} — {_employee_label(document.employee)}"
            record_access(
                session,
                user_id=account.user_id,
                document_id=document.id,
                action=AccessAction.DOWNLOAD,
                channel=AccessChannel.TELEGRAM,
            )
            session.commit()
        try:
            content = path.read_bytes()
        except OSError as exc:
            logger.error("Telegram belgesi okunamadı (%s)", type(exc).__name__)
            return TextReply(FILE_MISSING_TEXT)
        return Delivery(content, file_name, caption)


async def _send_text(
    bot: Bot, chat_id: int, text: str, *, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    if len(text) > _MAX_MESSAGE_LENGTH:
        text = text[: _MAX_MESSAGE_LENGTH - 1] + "…"
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    except TelegramError as exc:
        # Metin loga yazılmaz (ad, belge adı taşır).
        logger.error("Telegram iletisi gönderilemedi (%s)", type(exc).__name__)


async def _answer_callback(query: CallbackQuery, text: str | None) -> None:
    try:
        await query.answer(text=text, show_alert=text is not None)
    except TelegramError as exc:
        logger.error("Telegram seçimi yanıtlanamadı (%s)", type(exc).__name__)


async def _remove_keyboard(query: CallbackQuery) -> None:
    """Basılan sorunun düğmelerini kaldırır: seçim tek kullanımlıktır."""
    if not isinstance(query.message, Message):
        return  # ileti bota erişilemez (48 saatten eski) ya da yok: düzenlenemez
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError as exc:
        logger.error("Telegram seçim düğmeleri kaldırılamadı (%s)", type(exc).__name__)
