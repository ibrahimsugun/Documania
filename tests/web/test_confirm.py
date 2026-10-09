"""10.8.1 — iki aşamalı onay mekanizması: onay metinleri §20.6 tablosundan **birebir** kullanılır;
sunucu tek kullanımlık belirteç ister ve belirteçsiz isteği reddeder (K16, §20.6.1, §20.6.2).

Metinler PRD dosyasındaki tablonun kendisiyle karşılaştırılır: Türkçe kaynak §20.6'nın, İngilizce
ve Sırpça karşılıklar §20.6.3'ün tablosuyla birebir (10.10.4; PLAN.md §D92 h, §D96). Belirteç
kuralları doğrudan `app.web.confirm` üzerinde, geçici SQLite ile sınanır; panel ve API uçlarındaki
davranış `test_document_move.py`, `test_queue*.py` ve `test_upload_detail.py`'dedir; metnin isteğin
dilinde görünmesi `test_confirm_language.py`'dedir.

İstek dışı `first_text`/`second_text` çağrısı `en` görür (§D93 b); aşağıdaki testler Türkçe kaynağı
bekler, bu yüzden dosya `tr` bağlamında koşar.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

import app.web.confirm as confirm
from app.db.models import ConfirmationToken, Employee, Event, utcnow
from app.events import EventType
from app.i18n import SUPPORTED_LANGUAGES, translate, use_language
from app.web.auth import SESSION_COOKIE, PanelUser
from app.web.confirm import (
    CONFIRMATION_REFUSED,
    CONFIRMATION_TEXTS,
    CONFIRMATION_TEXTS_BY_LANGUAGE,
    ConfirmationRefusedError,
    ConfirmationTexts,
    Operation,
    confirm_operation,
    confirmation_texts,
    consume_confirmation,
    fill,
    first_text,
    issue_confirmation,
    second_text,
)
from tests.web.conftest import SESSION, SIGNED_IN

PRD = Path(__file__).resolve().parents[2] / "urun-gereksinim-dokumani-PRD.md"
# §20.6 tablosunun "İşlem" sütunu → mekanizmanın işlemi.
PRD_OPERATIONS = {
    "Belgeyi başka çalışana taşı": Operation.MOVE,
    "Kuyruk öğesini çalışana ata": Operation.ASSIGN,
    "Onay bekleyen profili onayla": Operation.APPROVE_PROFILE,
    "Yeni belge türünü onayla": Operation.APPROVE_TYPE,
    "Belgeyi arşive taşı": Operation.ARCHIVE,
    "Taramayı yoksay": Operation.DISMISS,
    "Çalışan profilini düzenle": Operation.EDIT_EMPLOYEE,  # 10.5.6, §D61 (tm 126)
    "Çalışanı pasife al": Operation.DEACTIVATE_EMPLOYEE,  # 10.5.7, §D61 (tm 127)
    "Çalışanı yeniden etkinleştir": Operation.REACTIVATE_EMPLOYEE,  # 10.5.7, §D61 (tm 127)
    "Profil alt kaydını kaldır": Operation.REMOVE_PROFILE_RECORD,  # 10.5.8, §D61 (tm 128)
    "İki çalışanı birleştir": Operation.MERGE_EMPLOYEES,  # 10.5.9, §D61 (tm 129)
    "Belgeyi arşivden geri al": Operation.UNARCHIVE,  # 10.5.10, §D61 (tm 130)
    "Kuyruk öğesini kapat": Operation.CLOSE_QUEUE_ITEM,  # 10.7.4, §D61 (tm 131)
    "Belgeyi kalıcı sil": Operation.DELETE_DOCUMENT,  # 10.5.12, §D110 (tm 166)
}
TARGET = "7:E0002"


def _section_20_6_rows() -> dict[str, tuple[str, str]]:
    text = PRD.read_text(encoding="utf-8")
    section = text[text.index("### 20.6 ") : text.index("#### 20.6.1")]
    rows = re.findall(r"^\| ([^|`]+?) \| `([^`]+)` \| `([^`]+)` \|$", section, re.M)
    return {name: (first, second) for name, first, second in rows}


def _section_20_6_3_rows() -> dict[str, dict[str, ConfirmationTexts]]:
    """§20.6.3 tablosu: işlem → dil (`en`, `sr`) → iki metin."""
    text = PRD.read_text(encoding="utf-8")
    start = text.index("#### 20.6.3 ")
    end = text.find("\n#", start + 10)  # sonraki başlık; bölüm belgenin sonundaysa dosya sonu
    section = text[start : end if end != -1 else len(text)]
    rows = re.findall(
        r"^\| ([^|`]+?) \| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \|$", section, re.M
    )
    return {
        name: {"en": ConfirmationTexts(en_1, en_2), "sr": ConfirmationTexts(sr_1, sr_2)}
        for name, en_1, en_2, sr_1, sr_2 in rows
    }


@pytest.fixture(autouse=True)
def _source_language() -> Iterator[None]:
    with use_language("tr"):
        yield


def _request(cookie: str | None = SESSION) -> Request:
    headers = [] if cookie is None else [(b"cookie", f"{SESSION_COOKIE}={cookie}".encode())]
    return Request({"type": "http", "headers": headers})


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


def _issue(session: Session, operation: Operation = Operation.MOVE, target: str = TARGET) -> str:
    token = issue_confirmation(session, _request(), SIGNED_IN, operation, target).token
    session.commit()
    return token


def _consume(
    session: Session,
    token: str | None,
    *,
    operation: Operation = Operation.MOVE,
    target: str = TARGET,
    cookie: str | None = SESSION,
    user: PanelUser = SIGNED_IN,
) -> confirm.ConfirmedAction:
    return consume_confirmation(session, _request(cookie), user, operation, target, token)


# --- §20.6: metinler birebir ----------------------------------------------------------------------


def test_the_texts_are_the_section_20_6_table_verbatim() -> None:
    rows = _section_20_6_rows()

    assert set(rows) == set(PRD_OPERATIONS)
    assert {
        PRD_OPERATIONS[name]: ConfirmationTexts(*texts) for name, texts in rows.items()
    } == CONFIRMATION_TEXTS


def test_the_english_and_serbian_texts_are_the_section_20_6_3_table_verbatim() -> None:
    rows = _section_20_6_3_rows()

    assert set(rows) == set(PRD_OPERATIONS)  # 14 işlem; tabloda olup kodda olmayan ya da tersi yok
    for language, table in (
        ("en", confirm.CONFIRMATION_TEXTS_EN),
        ("sr", confirm.CONFIRMATION_TEXTS_SR),
    ):
        assert {PRD_OPERATIONS[name]: texts[language] for name, texts in rows.items()} == table
        assert CONFIRMATION_TEXTS_BY_LANGUAGE[language] is table


def test_the_texts_are_kept_per_language_for_exactly_the_supported_languages() -> None:
    assert set(CONFIRMATION_TEXTS_BY_LANGUAGE) == set(SUPPORTED_LANGUAGES)
    assert CONFIRMATION_TEXTS_BY_LANGUAGE["tr"] is CONFIRMATION_TEXTS
    for table in CONFIRMATION_TEXTS_BY_LANGUAGE.values():
        assert set(table) == set(PRD_OPERATIONS.values())


def _placeholders(text: str) -> list[str]:
    return sorted(re.findall(r"<[^<>]+>", text))


@pytest.mark.parametrize("language", ["en", "sr"])
def test_every_language_keeps_the_placeholders_of_the_turkish_source(language: str) -> None:
    for operation, source in CONFIRMATION_TEXTS.items():
        texts = CONFIRMATION_TEXTS_BY_LANGUAGE[language][operation]
        assert _placeholders(texts.first) == _placeholders(source.first), operation
        assert _placeholders(texts.second) == _placeholders(source.second), operation
        assert texts.first != source.first and texts.second != source.second, operation


@pytest.mark.parametrize("language", list(SUPPORTED_LANGUAGES))
def test_every_language_fills_every_placeholder_with_the_same_values(language: str) -> None:
    values = {
        "name": "Ivan Petrov",
        "merged_name": "Ivan Petrow",
        "kept_name": "Ivan Petrov",
        "type_name": "Work permit",
        "count": 3,
        "documents": 4,
    }
    for operation in CONFIRMATION_TEXTS:
        for text in (
            first_text(operation, language=language, **values),
            second_text(operation, language=language, **values),
        ):
            assert not re.search(r"<[^<>]+>", text), (operation, text)
    assert first_text(Operation.ASSIGN, language=language, **values).count("Ivan Petrov") == 1
    assert "Ivan Petrow" in first_text(Operation.MERGE_EMPLOYEES, language=language, **values)
    assert "Work permit" in first_text(Operation.APPROVE_TYPE, language=language, **values)
    dismissed = second_text(Operation.DISMISS, language=language, queue_items=2, documents=0)
    assert "2" in dismissed and "0" in dismissed
    if language != "tr":
        assert "(2)" in dismissed and "(0)" in dismissed


@pytest.mark.parametrize("language", ["en", "sr"])
def test_a_missing_placeholder_value_is_refused_in_every_language(language: str) -> None:
    with pytest.raises(ValueError, match="<Ad Soyad>"):
        first_text(Operation.ASSIGN, language=language)
    with pytest.raises(ValueError, match="<Tür adı>"):
        first_text(Operation.APPROVE_TYPE, language=language)
    with pytest.raises(ValueError, match="<N>"):
        second_text(Operation.DISMISS, language=language, documents=1)
    with pytest.raises(ValueError, match="<M>"):
        second_text(Operation.DISMISS, language=language, queue_items=1)


def test_the_texts_follow_the_request_language_and_an_explicit_language_wins() -> None:
    expected = {
        "tr": "Bu belgeyi arşive taşımak üzeresiniz. Emin misiniz?",
        "en": "You are about to move this document to the archive. Are you sure?",
        "sr": "Upravo ćete premestiti ovaj dokument u arhivu. Da li ste sigurni?",
    }
    for language, text in expected.items():
        with use_language(language):
            assert first_text(Operation.ARCHIVE) == text
            assert confirmation_texts(Operation.ARCHIVE).first == text
    with use_language("en"):
        assert first_text(Operation.ARCHIVE, language="sr") == expected["sr"]
        assert second_text(Operation.ARCHIVE, language="tr") == (
            CONFIRMATION_TEXTS[Operation.ARCHIVE].second
        )
    with pytest.raises(ValueError, match="desteklenmeyen dil"):
        first_text(Operation.ARCHIVE, language="de")


def test_the_confirmation_refusal_is_source_text_and_translates_for_the_panel() -> None:
    assert CONFIRMATION_REFUSED.startswith("Onay geçersiz")
    assert translate(CONFIRMATION_REFUSED) == CONFIRMATION_REFUSED
    with use_language("en"):
        assert translate(CONFIRMATION_REFUSED) == (
            "Confirmation is invalid: the token is missing, expired, already used or does not "
            "belong to this action."
        )
    with use_language("sr"):
        assert translate(CONFIRMATION_REFUSED) == (
            "Potvrda nije važeća: token ne postoji, istekao je, već je iskorišćen ili ne pripada "
            "ovoj radnji."
        )


def test_placeholders_are_filled_at_run_time_and_never_shown_empty() -> None:
    assert first_text(Operation.ASSIGN, name="Kayitli Kisi") == (
        "Bu belgeyi Kayitli Kisi çalışanına atamak üzeresiniz. Emin misiniz?"
    )
    assert first_text(Operation.APPROVE_PROFILE, name="Test Ornekova").startswith(
        "Test Ornekova için yeni bir çalışan profili"
    )
    assert first_text(Operation.APPROVE_TYPE, type_name="Peru Diploması").startswith(
        "Peru Diploması belge türünü"
    )
    assert second_text(Operation.ARCHIVE) == CONFIRMATION_TEXTS[Operation.ARCHIVE].second
    assert first_text(Operation.MOVE) == CONFIRMATION_TEXTS[Operation.MOVE].first
    with pytest.raises(ValueError, match="<Ad Soyad>"):
        first_text(Operation.ASSIGN)
    with pytest.raises(ValueError, match="<Tür adı>"):
        fill("<Tür adı> belge türünü", name="Ad")


@pytest.mark.parametrize("language", list(SUPPORTED_LANGUAGES))
def test_the_deletion_counts_are_filled_in_every_language(language: str) -> None:
    # 10.5.12: <N> diskten silinecek dosya (`count`), <M> kalan dosya (`documents`); sıfır da
    # yazılır.
    text = second_text(Operation.DELETE_DOCUMENT, language=language, count=3, documents=0)
    assert "(3)" in text and "(0)" in text
    assert not re.search(r"<[^<>]+>", text)
    with pytest.raises(ValueError, match="<M>"):
        second_text(Operation.DELETE_DOCUMENT, language=language, count=3)


def test_the_dismissal_counts_are_filled_and_never_shown_empty() -> None:
    # 10.3.4: <N> bekleyen kuyruk öğesi, <M> yerinde kalan belge; sıfır da yazılır.
    assert second_text(Operation.DISMISS, queue_items=3, documents=0) == (
        "Parti ve bekleyen 3 kuyruk öğesi listelerden kalkacaktır; üretilmiş 0 belge yerinde "
        "kalır. Son kararınız mı?"
    )
    assert first_text(Operation.DISMISS) == "Bu taramayı yoksaymak üzeresiniz. Emin misiniz?"
    with pytest.raises(ValueError, match="<N>"):
        second_text(Operation.DISMISS, documents=1)
    with pytest.raises(ValueError, match="<M>"):
        second_text(Operation.DISMISS, queue_items=1)


def test_the_profile_edit_count_is_filled_and_never_shown_empty() -> None:
    # 10.5.6: <N> yeniden adlandırılacak belge dosyası; ad değişmiyorsa 0 yazılır.
    assert second_text(Operation.EDIT_EMPLOYEE, count=3) == (
        "Ad ya da soyad değiştiyse klasör ve 3 belge dosyası yeniden adlandırılacaktır. Son "
        "kararınız mı?"
    )
    assert "ve 0 belge dosyası" in second_text(Operation.EDIT_EMPLOYEE, count=0)
    assert first_text(Operation.EDIT_EMPLOYEE) == (
        "Bu çalışanın profil bilgilerini değiştirmek üzeresiniz. Emin misiniz?"
    )
    with pytest.raises(ValueError, match="<N>"):
        second_text(Operation.EDIT_EMPLOYEE)
    with pytest.raises(ValueError, match="ikisi birden"):
        second_text(Operation.DISMISS, queue_items=1, count=1, documents=1)


def test_the_status_change_names_the_employee_and_never_shows_the_placeholder() -> None:
    # 10.5.7: birinci metin çalışanın adını taşır, ikinci metin yer tutucusuzdur.
    assert first_text(Operation.DEACTIVATE_EMPLOYEE, name="Ivan Petrov") == (
        "Ivan Petrov çalışanını pasife almak üzeresiniz. Emin misiniz?"
    )
    assert first_text(Operation.REACTIVATE_EMPLOYEE, name="Ivan Petrov") == (
        "Ivan Petrov çalışanını yeniden etkinleştirmek üzeresiniz. Emin misiniz?"
    )
    assert second_text(Operation.DEACTIVATE_EMPLOYEE) == (
        "Bu çalışana gelen yeni belgeler otomatik yerleşmeyecek, kuyruğa düşecektir. Son "
        "kararınız mı?"
    )
    with pytest.raises(ValueError, match="<Ad Soyad>"):
        first_text(Operation.DEACTIVATE_EMPLOYEE)


def test_the_profile_record_removal_texts_carry_no_placeholder() -> None:
    # 10.5.8: iki metin de yer tutucusuzdur; kaydın değeri onay metnine girmez.
    assert first_text(Operation.REMOVE_PROFILE_RECORD) == (
        "Bu kaydı çalışan profilinden kaldırmak üzeresiniz. Emin misiniz?"
    )
    assert second_text(Operation.REMOVE_PROFILE_RECORD) == (
        "Kayıt eşleştirmede ve aramada kullanılmayacak, geçmişte kalacaktır. Son kararınız mı?"
    )
    assert Operation.REMOVE_PROFILE_RECORD.value == "remove_profile_record"


def test_the_merge_texts_name_both_records_and_count_the_documents() -> None:
    # 10.5.9: birinci metin birleşeni ve kalanı adlandırır, ikinci metin taşınacak belge sayısını
    # ve geri alınamazlığı söyler; boş yer tutucu kullanıcıya gitmez.
    assert first_text(
        Operation.MERGE_EMPLOYEES, merged_name="Ivan Petrow", kept_name="Ivan Petrov"
    ) == ("Ivan Petrow kaydını Ivan Petrov kaydıyla birleştirmek üzeresiniz. Emin misiniz?")
    assert second_text(Operation.MERGE_EMPLOYEES, count=0) == (
        "0 belge taşınacak ve birleşen kayıt kapanacaktır; bu işlem geri alınamaz. Son kararınız "
        "mı?"
    )
    with pytest.raises(ValueError, match="<Birleşen Ad Soyad>"):
        first_text(Operation.MERGE_EMPLOYEES, kept_name="Ivan Petrov")
    with pytest.raises(ValueError, match="<Kalan Ad Soyad>"):
        first_text(Operation.MERGE_EMPLOYEES, merged_name="Ivan Petrow")
    with pytest.raises(ValueError, match="<N>"):
        second_text(Operation.MERGE_EMPLOYEES)
    # `<Ad Soyad>` yer tutucusu birleştirme metninde yoktur; ad verilse de değişmez.
    assert "<Ad Soyad>" not in confirm.CONFIRMATION_TEXTS[Operation.MERGE_EMPLOYEES].first
    assert Operation.MERGE_EMPLOYEES.value == "merge_employees"


# --- §20.6.1: tek kullanımlık belirteç ------------------------------------------------------------


def test_a_token_is_random_stored_only_as_a_hash_and_valid_for_ten_minutes(
    session: Session,
) -> None:
    before = utcnow()
    first, second = _issue(session), _issue(session)

    rows = session.scalars(select(ConfirmationToken).order_by(ConfirmationToken.id)).all()
    assert first != second and len(first) >= 40
    assert [row.token_hash for row in rows] != [first, second]
    assert first not in str([vars(row) for row in rows])
    row = rows[0]
    assert (row.username, row.operation, row.target) == (SIGNED_IN.username, "move", TARGET)
    assert row.session_hash != SESSION and len(row.session_hash) == 64
    assert before <= row.created_at <= utcnow()
    assert row.expires_at - row.created_at == timedelta(minutes=10)
    assert row.consumed_at is None


def test_a_valid_token_is_consumed_once_with_both_confirmation_times(session: Session) -> None:
    token = _issue(session)

    confirmed = _consume(session, token)
    session.commit()

    assert confirmed.operation is Operation.MOVE and confirmed.target == TARGET
    assert confirmed.first_confirmed_at <= confirmed.second_confirmed_at <= utcnow()
    row = session.scalars(select(ConfirmationToken)).one()
    assert row.consumed_at == confirmed.second_confirmed_at
    with pytest.raises(ConfirmationRefusedError, match="daha önce kullanılmış"):
        _consume(session, token)


def test_a_rolled_back_operation_leaves_the_token_unconsumed(session: Session) -> None:
    # Tüketme çağıranın işlemindedir: işlem geri alınırsa aynı onaylanmış işlem yeniden denenir.
    token = _issue(session)
    _consume(session, token)
    session.rollback()

    assert _consume(session, token).target == TARGET


@pytest.mark.parametrize("token", [None, ""], ids=repr)
def test_a_request_without_a_token_is_refused(session: Session, token: str | None) -> None:
    with pytest.raises(ConfirmationRefusedError, match="Belirteç yok"):
        _consume(session, token)


def test_an_unknown_token_is_refused(session: Session) -> None:
    _issue(session)

    with pytest.raises(ConfirmationRefusedError, match="tanınmıyor"):
        _consume(session, "uydurma-belirtec")


def test_an_expired_or_not_yet_valid_token_is_refused(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _issue(session)
    issued = session.scalars(select(ConfirmationToken)).one().created_at

    monkeypatch.setattr(confirm, "utcnow", lambda: issued + timedelta(minutes=10, seconds=1))
    with pytest.raises(ConfirmationRefusedError, match="süresi geçmiş"):
        _consume(session, token)
    monkeypatch.setattr(confirm, "utcnow", lambda: issued - timedelta(seconds=1))
    with pytest.raises(ConfirmationRefusedError, match="süresi geçmiş"):
        _consume(session, token)
    monkeypatch.setattr(confirm, "utcnow", lambda: issued + timedelta(minutes=10))
    assert _consume(session, token).first_confirmed_at == issued  # sınırın içinde


def test_a_token_is_bound_to_its_session_and_its_user(session: Session) -> None:
    token = _issue(session)
    other_user = PanelUser(id=2, username="baska-yonetici", role="admin")

    with pytest.raises(ConfirmationRefusedError, match="oturuma ait değil"):
        _consume(session, token, cookie="oturum-iki")
    with pytest.raises(ConfirmationRefusedError, match="oturuma ait değil"):
        _consume(session, token, user=other_user)
    with pytest.raises(ConfirmationRefusedError, match="Oturum çerezi yok"):
        _consume(session, token, cookie=None)
    assert _consume(session, token).target == TARGET  # reddedilen denemeler tüketmez


def test_a_token_is_bound_to_its_operation_and_its_target(session: Session) -> None:
    token = _issue(session)

    with pytest.raises(ConfirmationRefusedError, match="bu işleme ait değil"):
        _consume(session, token, operation=Operation.ARCHIVE)
    with pytest.raises(ConfirmationRefusedError, match="bu işleme ait değil"):
        _consume(session, token, target="7:E0003")
    assert _consume(session, token).target == TARGET


def test_no_token_is_issued_without_a_session_cookie_or_for_a_bad_target(
    session: Session,
) -> None:
    with pytest.raises(ConfirmationRefusedError, match="Oturum çerezi yok"):
        issue_confirmation(session, _request(None), SIGNED_IN, Operation.MOVE, TARGET)
    for target in ("", "x" * 256):
        with pytest.raises(ValueError, match="Onay hedefi"):
            issue_confirmation(session, _request(), SIGNED_IN, Operation.MOVE, target)
    assert session.scalar(select(func.count()).select_from(ConfirmationToken)) == 0


# --- USER_CONFIRMED -----------------------------------------------------------------------------


def test_confirmation_logs_the_user_the_operation_the_target_and_both_times(
    session: Session,
) -> None:
    session.add(Employee(id="E0002", folder_name="Yeni_Sahip_E0002", given_names="Y", surname="S"))
    token = _issue(session)

    confirmed = confirm_operation(
        session,
        _request(),
        SIGNED_IN,
        Operation.MOVE,
        TARGET,
        token,
        event_target={"document_id": 7, "employee_id": "E0002"},
        document_id=None,
        employee_id="E0002",
    )
    session.commit()

    event = session.scalars(select(Event)).one()
    assert (event.type, event.actor, event.employee_id) == (
        EventType.USER_CONFIRMED.value,
        SIGNED_IN.username,
        "E0002",
    )
    assert event.data_json == {
        "operation": "move",
        "target": {"document_id": 7, "employee_id": "E0002"},
        "first_confirmed_at": confirmed.first_confirmed_at.isoformat(),
        "second_confirmed_at": confirmed.second_confirmed_at.isoformat(),
    }
    first = datetime.fromisoformat(event.data_json["first_confirmed_at"])
    assert first <= datetime.fromisoformat(event.data_json["second_confirmed_at"])


def test_a_refused_confirmation_logs_nothing(session: Session) -> None:
    _issue(session)

    with pytest.raises(ConfirmationRefusedError):
        confirm_operation(
            session,
            _request(),
            SIGNED_IN,
            Operation.MOVE,
            TARGET,
            "uydurma-belirtec",
            event_target={"document_id": 7},
        )

    assert session.scalars(select(Event)).all() == []
