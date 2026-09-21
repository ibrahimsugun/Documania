"""13.1.1 — maliyet paneli: sayfa, parti ve ay bazında token ve maliyet görünür; ön elemeli
sayfanın (13.2.1) tokenları her modelin kendi fiyatıyla hesaplanır.

Olaylar `record_event` ile yazılır (sayfa analizinin kendi yazdığı biçim: `data_json.usage`);
sayfalar `TestClient` ile çizilir. Sağlayıcı çağrısı ve ağ yoktur.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import ModelPrice, Settings, get_settings
from app.db.models import Event, Upload, UploadFile
from app.events import USAGE_BY_MODEL_DATA_KEY, USAGE_DATA_KEY, EventType, record_event
from app.web.routers.metrics import BATCH_LIMIT, UsageEvent

CLAUDE = "claude-test"
GPT = "gpt-test"
PRICES = {
    CLAUDE: ModelPrice(input_per_mtok=Decimal(5), output_per_mtok=Decimal(25)),
    GPT: ModelPrice(input_per_mtok=Decimal(1), output_per_mtok=Decimal(10)),
}


def _prices(app: FastAPI, prices: dict[str, ModelPrice] | None) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="sqlite://", ai_model_prices=prices or {}
    )


def _upload(session: Session, upload_id: str, *names: str) -> list[int]:
    """Partiyi ve dosyalarını yazar; dosya kimliklerini döner."""
    upload = Upload(id=upload_id, channel="web", status="done")
    session.add(upload)
    files = [
        UploadFile(
            upload=upload,
            original_name=name,
            stored_path=f"Inbox/{upload_id}/{name}",
            sha256="0" * 64,
            mime="application/pdf",
        )
        for name in names
    ]
    session.add_all(files)
    session.flush()
    return [upload_file.id for upload_file in files]


def _analysis(
    session: Session,
    upload_id: str,
    file_id: int,
    page_index: int,
    ts: datetime,
    *,
    model: str | None = CLAUDE,
    usage: tuple[int, int] | None = (1000, 100),
    failed: bool = False,
) -> None:
    data: dict[str, object] = {"provider": "test"}
    if model is not None:
        data["model"] = model
    if usage is not None:
        data[USAGE_DATA_KEY] = {"input_tokens": usage[0], "output_tokens": usage[1]}
    event = record_event(
        session,
        EventType.PAGE_ANALYSIS_FAILED if failed else EventType.PAGE_ANALYZED,
        upload_id=upload_id,
        file_id=file_id,
        page_index=page_index,
        data=data,
    )
    event.ts = ts


def _at(year: int, month: int, day: int = 15) -> datetime:
    return datetime(year, month, day, 10, 0, tzinfo=UTC)


def _section(html: str, section: str) -> str:
    block = re.search(rf'<section id="{section}".*?</section>', html, re.S)
    assert block is not None, section
    return block.group(0)


def _rows(html: str, section: str) -> list[list[str]]:
    """`<section id=...>` içindeki tablo satırlarının hücre metinleri (başlık satırı hariç)."""
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", _section(html, section), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if cells:
            rows.append([re.sub(r"<[^>]+>", "", cell).strip() for cell in cells])
    return rows


@pytest.fixture
def seeded(session_factory: sessionmaker[Session], app: FastAPI) -> None:
    """İki ay, iki parti, iki model; ağustosta bir başarısız ve bir ölçülmemiş analiz."""
    _prices(app, PRICES)
    with session_factory() as session:
        first_a, first_b = _upload(session, "u_20260820_0001", "a.pdf", "b.pdf")
        (second_a,) = _upload(session, "u_20260910_0002", "c.pdf")
        _analysis(session, "u_20260820_0001", first_a, 0, _at(2026, 8), usage=(1000, 100))
        _analysis(session, "u_20260820_0001", first_a, 1, _at(2026, 8), usage=(2000, 200))
        _analysis(
            session, "u_20260820_0001", first_b, 0, _at(2026, 8), usage=(500, 50), failed=True
        )
        _analysis(session, "u_20260820_0001", first_b, 1, _at(2026, 8), usage=None)
        _analysis(
            session, "u_20260910_0002", second_a, 0, _at(2026, 9), model=GPT, usage=(4000, 400)
        )
        session.commit()


# --- boş durum ve fiyat tanımı ----------------------------------------------------------------


def test_page_without_any_analysis_says_so(client: TestClient, app: FastAPI) -> None:
    _prices(app, PRICES)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "<title>Maliyet · belgeee</title>" in response.text
    assert response.text.count("Henüz sayfa analizi yok.") == 2
    assert _rows(response.text, "total") == [["Toplam", "0", "0", "0", "0", "—", "0"]]
    assert _rows(response.text, "months") == []
    assert _rows(response.text, "batches") == []


def test_model_in_neither_env_nor_the_builtin_table_counts_tokens_and_cost_is_not_invented(
    client: TestClient, app: FastAPI, seeded: None
) -> None:
    # `AI_MODEL_PRICES` boş; test modelleri yerleşik tabloda da yok (C77: fiyat uydurulmaz).
    _prices(app, None)

    response = client.get("/metrics")

    assert "Fiyatı tanımlı olmayan model: claude-test, gpt-test" in response.text
    assert "Yerleşik fiyat tablosunda yok" in response.text
    assert "AI_MODEL_PRICES" in response.text
    (total,) = _rows(response.text, "total")
    assert total == ["Toplam", "5", "7.500", "750", "8.250", "—", "1"]
    assert "USD</td>" not in _section(response.text, "total")
    assert [row[:3] for row in _rows(response.text, "prices")] == [
        ["claude-test", "—", "fiyat yok"],
        ["gpt-test", "—", "fiyat yok"],
    ]


# --- ay, parti ve toplam ----------------------------------------------------------------------


def test_months_are_listed_newest_first_with_tokens_and_cost(
    client: TestClient, seeded: None
) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert _rows(response.text, "months") == [
        # eylül: 4000 girdi × 1 + 400 çıktı × 10 = 8000 / 1e6
        ["2026-09", "1", "4.000", "400", "4.400", "0.0080 USD", "0"],
        # ağustos: (1000+2000+500) × 5 + (100+200+50) × 25 = 26250 / 1e6; biri ölçülmemiş
        ["2026-08", "4", "3.500", "350", "3.850", "0.0263 USD", "1"],
    ]


def test_total_row_sums_every_month(client: TestClient, seeded: None) -> None:
    response = client.get("/metrics")

    (total,) = _rows(response.text, "total")
    assert total == ["Toplam", "5", "7.500", "750", "8.250", "0.0343 USD", "1"]
    assert "1 analizin token kaydı yok" in response.text
    assert "Token fiyatı tanımlı değil" not in response.text


def test_batches_are_listed_newest_first_and_link_to_their_pages(
    client: TestClient, seeded: None
) -> None:
    response = client.get("/metrics")

    assert _rows(response.text, "batches") == [
        ["u_20260910_0002", "1", "4.000", "400", "4.400", "0.0080 USD", "0"],
        ["u_20260820_0001", "4", "3.500", "350", "3.850", "0.0263 USD", "1"],
    ]
    assert 'href="/metrics/uploads/u_20260910_0002"' in response.text
    assert 'href="/metrics/uploads/u_20260820_0001"' in response.text


def test_failed_pages_spend_tokens_too(client: TestClient, seeded: None) -> None:
    response = client.get("/metrics/uploads/u_20260820_0001")

    rows = {row[0]: row for row in _rows(response.text, "pages")}
    assert rows["b.pdf — sayfa 1"][2:6] == ["500", "50", "550", "0.0038 USD"]


def test_month_is_taken_from_the_utc_timestamp(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, PRICES)
    with session_factory() as session:
        (file_id,) = _upload(session, "u_20260930_0003", "gece.pdf")
        _analysis(
            session, "u_20260930_0003", file_id, 0, datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC)
        )
        _analysis(
            session, "u_20260930_0003", file_id, 1, datetime(2026, 10, 1, 0, 0, 1, tzinfo=UTC)
        )
        session.commit()

    response = client.get("/metrics")

    assert [row[:2] for row in _rows(response.text, "months")] == [
        ["2026-10", "1"],
        ["2026-09", "1"],
    ]


def test_only_page_analysis_events_are_counted(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, PRICES)
    with session_factory() as session:
        (file_id,) = _upload(session, "u_20260910_0004", "d.pdf")
        _analysis(session, "u_20260910_0004", file_id, 0, _at(2026, 9))
        # Kullanım alanı taşısa da sayfa analizi olmayan olay ölçüme girmez.
        record_event(
            session,
            EventType.PLAN_CREATED,
            upload_id="u_20260910_0004",
            data={USAGE_DATA_KEY: {"input_tokens": 999999, "output_tokens": 999999}},
        )
        session.commit()

    (total,) = _rows(client.get("/metrics").text, "total")

    assert total[:5] == ["Toplam", "1", "1.000", "100", "1.100"]


def test_broken_usage_data_reads_as_unmeasured(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, PRICES)
    with session_factory() as session:
        (file_id,) = _upload(session, "u_20260910_0005", "e.pdf")
        event = record_event(
            session,
            EventType.PAGE_ANALYZED,
            upload_id="u_20260910_0005",
            file_id=file_id,
            page_index=0,
            data={"model": CLAUDE, USAGE_DATA_KEY: {"input_tokens": "çok", "output_tokens": 5}},
        )
        event.ts = _at(2026, 9)
        session.commit()

    response = client.get("/metrics")

    assert response.status_code == 200
    assert _rows(response.text, "total") == [["Toplam", "1", "0", "0", "0", "—", "1"]]


# --- fiyatı olmayan model ---------------------------------------------------------------------


def test_model_without_a_price_counts_tokens_but_not_cost(
    client: TestClient, app: FastAPI, seeded: None
) -> None:
    _prices(app, {CLAUDE: PRICES[CLAUDE]})

    response = client.get("/metrics")

    assert "Fiyatı tanımlı olmayan model: gpt-test" in response.text
    # Eylül yalnız fiyatsız modelle yapıldı: tokenlar var, maliyet yok. Ağustos tam fiyatlı.
    assert _rows(response.text, "months") == [
        ["2026-09", "1", "4.000", "400", "4.400", "—", "0"],
        ["2026-08", "4", "3.500", "350", "3.850", "0.0263 USD", "1"],
    ]
    (total,) = _rows(response.text, "total")
    assert total[5] == "en az 0.0263 USD"


def test_analysis_without_a_model_name_is_priced_as_unknown(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, PRICES)
    with session_factory() as session:
        (file_id,) = _upload(session, "u_20260910_0006", "f.pdf")
        _analysis(session, "u_20260910_0006", file_id, 0, _at(2026, 9), model=None)
        session.commit()

    response = client.get("/metrics")

    assert "(model adı yok)" in response.text
    assert _rows(response.text, "total")[0][2:6] == ["1.000", "100", "1.100", "—"]


# --- ucuz model ön elemesi (13.2.1): bir sayfa iki modele harcatır --------------------------------


def _split(
    session: Session,
    upload_id: str,
    usage: tuple[int, int],
    by_model: object,
    *,
    model: str = CLAUDE,
) -> None:
    (file_id,) = _upload(session, upload_id, "h.pdf")
    event = record_event(
        session,
        EventType.PAGE_ANALYZED,
        upload_id=upload_id,
        file_id=file_id,
        page_index=0,
        data={
            "model": model,
            USAGE_DATA_KEY: {"input_tokens": usage[0], "output_tokens": usage[1]},
            USAGE_BY_MODEL_DATA_KEY: by_model,
        },
    )
    event.ts = _at(2026, 9)
    session.commit()


def test_prescreened_page_prices_each_model_s_share_at_its_own_price(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, PRICES)
    with session_factory() as session:
        _split(
            session,
            "u_20260910_0010",
            (1500, 150),
            {
                GPT: {"input_tokens": 500, "output_tokens": 50},
                CLAUDE: {"input_tokens": 1000, "output_tokens": 100},
            },
        )

    response = client.get("/metrics/uploads/u_20260910_0010")

    # GPT: 500 × 1 + 50 × 10 = 1000; Claude: 1000 × 5 + 100 × 25 = 7500 → 8500 / 1e6.
    # Toplamın tümü Claude fiyatıyla 0.0113 USD olurdu.
    assert _rows(response.text, "pages") == [
        ["h.pdf — sayfa 1", "1", "1.500", "150", "1.650", "0.0085 USD", "0", f"{CLAUDE}, {GPT}"]
    ]


def test_share_of_a_model_without_a_price_makes_the_cost_a_lower_bound(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, {CLAUDE: PRICES[CLAUDE]})
    with session_factory() as session:
        _split(
            session,
            "u_20260910_0011",
            (1500, 150),
            {
                GPT: {"input_tokens": 500, "output_tokens": 50},
                CLAUDE: {"input_tokens": 1000, "output_tokens": 100},
            },
        )

    response = client.get("/metrics")

    assert _rows(response.text, "total")[0][2:6] == ["1.500", "150", "1.650", "en az 0.0075 USD"]
    assert "Fiyatı tanımlı olmayan model: gpt-test" in response.text


def test_unmetered_event_has_no_shares_to_price() -> None:
    event = UsageEvent(
        ts=_at(2026, 9), upload_id=None, file_id=None, page_index=None, model=CLAUDE, usage=None
    )

    assert event.shares() == ()


@pytest.mark.parametrize(
    "by_model",
    [
        {GPT: {"input_tokens": 500, "output_tokens": 50}},
        {GPT: {"input_tokens": "çok", "output_tokens": 50}},
        {GPT: None, CLAUDE: {"input_tokens": 1500, "output_tokens": 150}},
        {"": {"input_tokens": 1500, "output_tokens": 150}},
        [["gpt-test", 1500, 150]],
        {},
    ],
    ids=["toplam-tutmuyor", "bozuk-sayi", "bozuk-pay", "adsiz-model", "sozluk-degil", "bos"],
)
def test_broken_model_split_is_ignored_and_the_total_goes_to_the_event_s_model(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session], by_model: object
) -> None:
    _prices(app, PRICES)
    with session_factory() as session:
        _split(session, "u_20260910_0012", (1500, 150), by_model)

    response = client.get("/metrics")

    # 1500 × 5 + 150 × 25 = 11250 / 1e6
    assert _rows(response.text, "total")[0][2:6] == ["1.500", "150", "1.650", "0.0113 USD"]


# --- parti sayfası ----------------------------------------------------------------------------


def test_upload_page_lists_pages_with_reanalyses_summed(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, PRICES)
    with session_factory() as session:
        first, second = _upload(session, "u_20260910_0007", "on.pdf", "arka.pdf")
        _analysis(session, "u_20260910_0007", first, 0, _at(2026, 9, 10), usage=(1000, 100))
        _analysis(session, "u_20260910_0007", first, 0, _at(2026, 9, 11), usage=(1200, 120))
        _analysis(
            session, "u_20260910_0007", second, 2, _at(2026, 9, 10), model=GPT, usage=(300, 30)
        )
        session.commit()

    response = client.get("/metrics/uploads/u_20260910_0007")

    assert response.status_code == 200
    assert "<title>Maliyet · u_20260910_0007 · belgeee</title>" in response.text
    assert _rows(response.text, "pages") == [
        ["on.pdf — sayfa 1", "2", "2.200", "220", "2.420", "0.0165 USD", "0", CLAUDE],
        ["arka.pdf — sayfa 3", "1", "300", "30", "330", "0.0006 USD", "0", GPT],
    ]
    assert 'href="/uploads/u_20260910_0007"' in response.text
    assert "Toplam token" in response.text


def test_upload_page_counts_only_its_own_events(client: TestClient, seeded: None) -> None:
    response = client.get("/metrics/uploads/u_20260910_0002")

    assert [row[0] for row in _rows(response.text, "pages")] == ["c.pdf — sayfa 1"]
    assert "4.400" in response.text


def test_upload_without_analysis_events_says_so(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _upload(session, "u_20260910_0008", "g.pdf")
        session.commit()

    response = client.get("/metrics/uploads/u_20260910_0008")

    assert response.status_code == 200
    assert "Bu partide sayfa analizi kaydı yok." in response.text


def test_unknown_upload_is_a_404_page(client: TestClient) -> None:
    response = client.get("/metrics/uploads/yok")

    assert response.status_code == 404
    assert "Parti bulunamadı." in response.text
    assert "<table" not in response.text


# --- görünüm ----------------------------------------------------------------------------------


def test_batch_table_is_capped_and_says_how_many_batches_exist(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, PRICES)
    total = BATCH_LIMIT + 3
    with session_factory() as session:
        for number in range(total):
            upload_id = f"u_20260910_{number + 100:04d}"
            (file_id,) = _upload(session, upload_id, "h.pdf")
            _analysis(session, upload_id, file_id, 0, _at(2026, 9, 1 + number % 28))
        session.commit()

    response = client.get("/metrics")

    assert len(_rows(response.text, "batches")) == BATCH_LIMIT
    assert (
        f"En son analiz edilen {BATCH_LIMIT} parti listelendi ({total} partiden)." in response.text
    )
    (grand_total,) = _rows(response.text, "total")
    assert grand_total[1] == str(total)


def test_topbar_links_to_the_page_and_marks_it_active(client: TestClient, app: FastAPI) -> None:
    _prices(app, PRICES)

    other = client.get("/queues")
    assert '<a class="tool-link" href="/metrics">Maliyet</a>' in other.text

    metrics = client.get("/metrics")
    assert (
        '<a class="tool-link active" href="/metrics" aria-current="page">Maliyet</a>'
        in metrics.text
    )
    # Ana menü beş bölümdür (10.1.1); maliyet menüde değil, oturumun yanındadır.
    assert 'href="/metrics"' not in re.search(
        r'<nav class="menu".*?</nav>', metrics.text, re.S
    ).group(0)


def test_pages_only_read(
    client: TestClient, seeded: None, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        before = session.scalar(select(func.count()).select_from(Event))

    for path in ("/metrics", "/metrics/uploads/u_20260820_0001", "/metrics/uploads/yok"):
        client.get(path)

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == before


# --- yerleşik fiyat tablosu (C77) -------------------------------------------------------------

LUNA = "gpt-5.6-luna"


def _usage_event(
    session_factory: sessionmaker[Session],
    upload_id: str,
    model: str,
    usage: dict[str, int],
) -> None:
    with session_factory() as session:
        (file_id,) = _upload(session, upload_id, "a.pdf")
        event = record_event(
            session,
            EventType.PAGE_ANALYZED,
            upload_id=upload_id,
            file_id=file_id,
            page_index=0,
            data={"provider": "openai", "model": model, USAGE_DATA_KEY: usage},
        )
        event.ts = _at(2026, 9)
        session.commit()


def test_real_model_is_priced_from_the_builtin_table_without_any_env_price(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, None)
    # Canlı denemenin toplamı (gpt-5.6-luna): 52724 × 0.2 + 1853 × 1.2 = 12768.4 / 1e6.
    _usage_event(
        session_factory, "u_20260920_0001", LUNA, {"input_tokens": 52724, "output_tokens": 1853}
    )

    response = client.get("/metrics")

    (total,) = _rows(response.text, "total")
    assert total == ["Toplam", "1", "52.724", "1.853", "54.577", "0.0128 USD", "0"]
    assert "Token fiyatı tanımlı değil" not in response.text
    assert "Fiyatı tanımlı olmayan model" not in response.text
    assert _rows(response.text, "prices") == [
        [LUNA, LUNA, "yerleşik tablo", "0.2 USD", "0.02 USD", "1.2 USD", "52.724", "0", "1.853"]
    ]


def test_cached_input_is_priced_at_the_cached_rate_on_the_page(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, None)
    # (2000 × 0.2 + 8000 × 0.02 + 1000 × 1.2) / 1e6 = 0.00176 → 0.0018
    _usage_event(
        session_factory,
        "u_20260920_0002",
        LUNA,
        {"input_tokens": 10_000, "output_tokens": 1000, "cached_input_tokens": 8000},
    )

    response = client.get("/metrics")

    (total,) = _rows(response.text, "total")
    assert total[2] == "10.000"
    assert total[5] == "0.0018 USD"
    (price,) = _rows(response.text, "prices")
    assert price[6:] == ["10.000", "8.000", "1.000"]


def test_env_price_overrides_the_builtin_table_and_says_so(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, {LUNA: ModelPrice(input_per_mtok=Decimal(1), output_per_mtok=Decimal(10))})
    _usage_event(
        session_factory, "u_20260920_0003", LUNA, {"input_tokens": 1000, "output_tokens": 100}
    )

    response = client.get("/metrics")

    (total,) = _rows(response.text, "total")
    assert total[5] == "0.0020 USD"  # 1000 × 1 + 100 × 10
    (price,) = _rows(response.text, "prices")
    assert price[:6] == [LUNA, LUNA, ".env (AI_MODEL_PRICES)", "1 USD", "girdi fiyatıyla", "10 USD"]


def test_dated_model_name_is_priced_by_its_base_model(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, None)
    _usage_event(
        session_factory,
        "u_20260920_0004",
        "claude-haiku-4-5-20251001",
        {"input_tokens": 1000, "output_tokens": 1000},
    )

    response = client.get("/metrics")

    (total,) = _rows(response.text, "total")
    assert total[5] == "0.0060 USD"  # 1000 × 1 + 1000 × 5
    (price,) = _rows(response.text, "prices")
    assert price[:3] == ["claude-haiku-4-5-20251001", "claude-haiku-4-5", "yerleşik tablo"]


def test_price_section_names_the_table_date_and_its_sources(
    client: TestClient, app: FastAPI
) -> None:
    _prices(app, None)

    response = client.get("/metrics")

    section = _section(response.text, "prices")
    assert "Henüz fiyatlanacak kullanım yok." in section
    assert "Yerleşik tablo 2026-09-18 tarihli" in section
    for provider in ("openai", "anthropic", "google", "deepseek"):
        assert f'href="https://benchlm.ai/{provider}/api-pricing"' in section


def test_upload_page_shows_the_prices_it_used(
    client: TestClient, app: FastAPI, session_factory: sessionmaker[Session]
) -> None:
    _prices(app, None)
    _usage_event(
        session_factory, "u_20260920_0005", LUNA, {"input_tokens": 1000, "output_tokens": 100}
    )

    response = client.get("/metrics/uploads/u_20260920_0005")

    assert response.status_code == 200
    rows = _rows(response.text, "pages")
    assert rows[0][5] == "0.0003 USD"  # 1000 × 0.2 + 100 × 1.2 = 320 / 1e6
    assert _rows(response.text, "prices")[0][:3] == [LUNA, LUNA, "yerleşik tablo"]
