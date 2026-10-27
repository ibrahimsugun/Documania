"""Eğitim komutları: "AI kararı" örneklerinin çift incelemesi (PRD 11.9.4; PLAN.md §D128) ve
örnek önizlemelerinin toplu ısıtılması (PRD 11.9.7; PLAN.md §D130).

    python -m app.training recheck [--limit N] [--dry-run] [--again] [--report YOL]
    python -m app.training previews

`previews` bütün türlerin bütün örneklerinin küçük ve büyük önizlemesini `cache/previews/` altına
üretir (`app.storage.previews.warm_previews`); var olanı atlar, durdurulursa yeniden çalıştırınca
kaldığı yerden sürer, sonda üretilen/var olan/üretilemeyen sayılarını yazar. Yapay zekâ çağırmaz.

Etkin "AI kararı" örneklerini GPT-6.1 Sol ve Claude Sonnet 5.5 (ikisi `low`) ile ayrı ayrı
sınıflandırır (`app.training.recheck`): ikisi örneğin türünü verirse etiket "doğrulanmış" olur;
ikisi başka ama aynı türü verirse örnek o türe taşınıp doğrulanır; farklıysalar ya da biri
belirleyemezse örnek "AI kararı" kalır. Her örnek tek işlemde commit edilir; durdurulan koşu
kaldığı yerden sürer
(rapor dosyasındaki örnekler `--again` verilmedikçe atlanır). `--dry-run` hiçbir şey yazmaz ama
yapay zekâ çağrıları yine ücretlidir. Sonda sonuç sayıları ve her model için belirteç ile tahmini
maliyet yazılır. İki sağlayıcının anahtarı da `.env`'de tanımlı olmalıdır.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.db.models import ExampleFileRecord
from app.db.session import create_db_engine, create_session_factory
from app.storage import DataLayout
from app.storage.previews import warm_previews
from app.training.known_types import load_known_types
from app.training.pair import (
    PRICES_DATE,
    PRICES_USD_PER_MILLION_TOKENS,
    ReviewPair,
    build_review_pair,
)
from app.training.recheck import (
    RecheckOutcome,
    RecheckResult,
    pending_examples,
    recheck_example,
    summarize,
    usage_of,
)

DEFAULT_REPORT = "_egitim/cift_inceleme.jsonl"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.training",
        description='"AI kararı" örneklerini Sol + Sonnet çift incelemesiyle yeniden kontrol eder',
    )
    commands = parser.add_subparsers(dest="command", required=True)
    recheck = commands.add_parser(
        "recheck", help='"AI kararı" örneklerini çift incelemeden geçirir'
    )
    recheck.add_argument("--limit", type=int, help="en çok bu kadar örnek (varsayılan: hepsi)")
    recheck.add_argument("--dry-run", action="store_true", help="hiçbir şey yazma, yalnız raporla")
    recheck.add_argument("--again", action="store_true", help="raporda olanları da yeniden incele")
    recheck.add_argument(
        "--report",
        type=Path,
        help=f"JSON satırları raporu (varsayılan: veri dizini/{DEFAULT_REPORT})",
    )
    commands.add_parser("previews", help="örnek önizlemelerini önceden üretir (toplu ısıtma)")
    return parser


def _previews() -> int:
    layout = DataLayout(get_settings().data_dir)
    counts = warm_previews(layout)
    print(json.dumps(counts, ensure_ascii=False))
    return 0


def _done_ids(report: Path) -> set[int]:
    if not report.exists():
        return set()
    done: set[int] = set()
    for line in report.read_text(encoding="utf-8").splitlines():
        if line.strip():
            done.add(int(json.loads(line)["example_id"]))
    return done


def _cost_lines(pair: ReviewPair) -> list[str]:
    lines = []
    total = 0.0
    for model, usage in usage_of(pair).items():
        prices = PRICES_USD_PER_MILLION_TOKENS.get(model)
        cost = (
            usage.input_tokens * prices[0] + usage.output_tokens * prices[1]
            if prices is not None
            else None
        )
        if cost is not None:
            cost /= 1_000_000
            total += cost
        shown = f"~{cost:.2f} USD" if cost is not None else "fiyat tanımsız"
        lines.append(
            f"{model}: {usage.calls} çağrı, girdi {usage.input_tokens:,} · çıktı "
            f"{usage.output_tokens:,} belirteç · {shown}"
        )
    lines.append(f"Toplam ~{total:.2f} USD (liste fiyatı, {PRICES_DATE})")
    return lines


def _recheck(args: argparse.Namespace) -> int:
    settings = get_settings()
    pair = build_review_pair(settings)
    if pair is None:
        print(
            "Çift inceleme kurulamadı: iki sağlayıcının anahtarı da tanımlı olmalı ve "
            "TRAINING_AUTO_CONFIRM kapalı olmamalı.",
            file=sys.stderr,
        )
        return 2
    layout = DataLayout(settings.data_dir)
    report = args.report or layout.root / DEFAULT_REPORT
    report.parent.mkdir(parents=True, exist_ok=True)
    skip = set() if args.again else _done_ids(report)
    factory = create_session_factory(create_db_engine(settings.database_url))
    with factory() as session:
        ids = [e.id for e in pending_examples(session) if e.id not in skip]
        session.rollback()
    if args.limit is not None:
        ids = ids[: args.limit]
    print(f"İncelenecek örnek: {len(ids)}", file=sys.stderr, flush=True)

    results: list[RecheckResult] = []
    for number, example_id in enumerate(ids, start=1):
        with factory() as session:
            example = session.get_one(ExampleFileRecord, example_id)
            known = load_known_types(session)
            result = recheck_example(
                session, layout, settings, known, pair, example, apply=not args.dry_run
            )
            if result.outcome is RecheckOutcome.ERROR or args.dry_run:
                session.rollback()
            else:
                session.commit()
        results.append(result)
        with report.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "example_id": result.example_id,
                        "from": result.current_slug,
                        "first": result.first_slug,
                        "second": result.second_slug,
                        "outcome": result.outcome.value,
                        "error": result.error,
                        "dry_run": args.dry_run,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        if number % 10 == 0 or number == len(ids):
            print(
                f"İncelendi: {number}/{len(ids)} {summarize(results)}",
                file=sys.stderr,
                flush=True,
            )

    print(json.dumps(summarize(results), ensure_ascii=False))
    for line in _cost_lines(pair):
        print(line)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "recheck":
        return _recheck(args)
    if args.command == "previews":
        return _previews()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
