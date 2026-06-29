"""폐지 ticker→cik 복구(A1) — 생존편향-안전 재무 팩터의 전제.

SEC `company_tickers.json` 은 현재 신고사만 → 폐지종목 ticker→cik 매핑 부재. 단 cik 만 알면
companyfacts 가 폐지사의 과거 신고를 PIT-correct(filed≤t) 반환. 이 모듈이 폐지 ticker 의 cik 를
복구해 A2 PIT ticker_history 의 폐지행 입력을 만든다. **delisted_date 동반**(ticker 재사용 구분 —
같은 ticker 가 폐지 후 타사에 재할당될 수 있어 폐지일이 엔티티 식별 키).

cik 소스(주입): 1차 EODHD ID-Mapping(`EodhdSource.fetch_id_mapping`·Free 플랜 포함). 폐지 커버<80%면
SEC `cik-lookup-data.txt`(회사명 기반·후속). 미커버 ticker = 제외(카운트 로그·추측 금지).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

logger = logging.getLogger(__name__)

_FILE_NAME = "delisted_cik.json"


def resolve_delisted_ciks(
    fetch_cik: Callable[[str], str | None],
    delisted: list[tuple[str, date]],
) -> dict[str, tuple[str, date]]:
    """폐지 (ticker, delisted_date) → {ticker: (cik, delisted_date)}.

    `fetch_cik(ticker)` 가 cik(str) 반환하면 채택, None 이면 제외(미커버 — 카운트 로그). 순수 함수
    (네트워크 의존 없음·호출부가 fetch_cik 에 EODHD/SEC 주입). 결과는 cik 해소된 폐지종목만.
    """
    result: dict[str, tuple[str, date]] = {}
    missing = 0
    for ticker, delisted_date in delisted:
        cik = fetch_cik(ticker)
        if cik is None:
            missing += 1
            continue
        result[ticker] = (cik, delisted_date)
    logger.info(
        "폐지 cik 복구: 입력=%d, 해소=%d, 미커버=%d", len(delisted), len(result), missing
    )
    return result


def select_delisted_sample(
    stocks: list[dict[str, object]], n: int
) -> list[tuple[str, date]]:
    """정지점1 라이브 probe 모집단 추출 — 폐지(delisted_at≠null) ∧ cik 미해소 종목 n개.

    모집단 = 생존편향 갭(SEC `company_tickers.json` 현재 신고사만 → 폐지사 cik 부재). cik 해소된
    폐지사(클래스주 등)는 제외(이미 복구 불요). **ticker 정렬 후 균등 stride** 추출 —
    알파벳/거래소/시대 편중 회피(첫 n개면 'A' 군집)·**결정적**(라이브 0·재현 가능). n≥모집단=전체.
    """
    population: list[tuple[str, date]] = []
    for stock in stocks:
        delisted_raw = stock.get("delisted_at")
        if not isinstance(delisted_raw, str) or not delisted_raw:
            continue  # 현재사(폐지 아님) — 제외
        if stock.get("cik"):
            continue  # cik 이미 해소(갭 아님) — 제외
        population.append((str(stock["ticker"]), date.fromisoformat(delisted_raw)))
    population.sort(key=lambda pair: pair[0])
    if n <= 0:
        return []
    if n >= len(population):
        return population
    stride = len(population) // n
    return [population[i * stride] for i in range(n)]


def store_delisted_ciks(mapping: dict[str, tuple[str, date]], base_dir: Path) -> Path:
    """`{ticker:(cik,delisted_date)}` → `base_dir/edgar/delisted_cik.json`(사람 읽기·교차검증 가능).

    형식: `{ticker: {cik, delisted_date(ISO)}}`. cik 는 SEC 퍼블릭도메인이라 영구보관 합법
    (EODHD 약관=해지 후 삭제이나 cik-lookup-data.txt 교차검증 전제). 반환=경로.
    """
    out_dir = base_dir / "edgar"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        ticker: {"cik": cik, "delisted_date": delisted_date.isoformat()}
        for ticker, (cik, delisted_date) in mapping.items()
    }
    path = out_dir / _FILE_NAME
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("폐지 cik 저장: %d종목 → %s", len(mapping), path)
    return path


def load_delisted_ciks(base_dir: Path) -> dict[str, tuple[str, date]]:
    """저장본 로드 → `{ticker:(cik,delisted_date)}`. 파일 없으면 빈 맵(미실행 정상)."""
    path = base_dir / "edgar" / _FILE_NAME
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(ticker): (str(rec["cik"]), date.fromisoformat(str(rec["delisted_date"])))
        for ticker, rec in payload.items()
    }


def main() -> int:
    """`python -m stockpick.data.cik_mapping [--sample N|--resolve-all]` — probe·전체 복구.

    `--sample N`(기본): 폐지+cik미해소 표본 N개 ID-Mapping 라이브 → 커버율 측정(**저장 안 함** —
    부분이 A2 입력으로 오인 방지). `--resolve-all`: 전체 모집단 복구 → `edgar/delisted_cik.json`
    저장(A1 산출물·A2 폐지행 소비). 정지점1 판정=ID-Mapping 단독(in-scope 91.7%·미커버=구조적
    비-XBRL). 키 비노출(configure_logging G6 가드)·라이브 호출.
    """
    import argparse
    import os
    from pathlib import Path

    from . import configure_logging
    from .eodhd import EodhdSource, _to_symbol

    parser = argparse.ArgumentParser(description="폐지 cik 복구(EODHD ID-Mapping)")
    parser.add_argument("--sample", type=int, default=50, help="probe 표본 크기(기본 50)")
    parser.add_argument(
        "--resolve-all", action="store_true", help="전체 복구→delisted_cik.json 저장"
    )
    ns = parser.parse_args()

    configure_logging()  # G6 — httpx api_token URL 로깅 차단(BLOCKING·라이브)
    base_dir = Path(os.environ.get("STOCKPICK_DATA_DIR", "data/parquet"))
    payload = json.loads((base_dir / "stock_snapshot.json").read_text(encoding="utf-8"))
    stocks = payload["stocks"]
    population = sum(
        1
        for s in stocks
        if isinstance(s.get("delisted_at"), str) and s.get("delisted_at") and not s.get("cik")
    )
    # resolve-all=전체(저장)·아니면 probe 표본(저장 안 함). select_delisted_sample(n≥pop)=전체.
    sample = select_delisted_sample(stocks, population if ns.resolve_all else ns.sample)

    source = EodhdSource()
    resolved = resolve_delisted_ciks(lambda t: source.fetch_id_mapping(_to_symbol(t)), sample)

    n = len(sample)
    hit = len(resolved)
    rate = hit / n if n else 0.0
    miss = [ticker for ticker, _ in sample if ticker not in resolved]
    if ns.resolve_all:
        path = store_delisted_ciks(resolved, base_dir)
        print(  # noqa: T201 — 진입점 사용자 출력(cik 은 SEC 퍼블릭도메인·키 아님)
            "[resolve-all] 폐지 cik 전체 복구 — EODHD ID-Mapping\n"
            f"  모집단(폐지+cik미해소): {population:,}  해소: {hit:,} ({rate:.1%})"
            f"  미커버: {len(miss):,}\n"
            f"  저장: {path}"
        )
        return 0
    verdict = (
        "≥80% → ID-Mapping 단독 채택 권장"
        if rate >= 0.80
        else "<80% → SEC cik-lookup-data.txt fallback 추가 필요"
    )
    hit_examples = [f"{t}→{cik}" for t, (cik, _) in list(resolved.items())[:5]]
    print(  # noqa: T201 — 진입점 사용자 출력(cik 은 SEC 퍼블릭도메인·키 아님)
        "[probe] 폐지 cik 복구 라이브 실측 — EODHD ID-Mapping\n"
        f"  표본: {n} / 모집단(폐지+cik미해소): {population:,}\n"
        f"  해소: {hit} ({rate:.1%})  미커버: {len(miss)}\n"
        f"  판정: {verdict}\n"
        f"  해소 예시: {', '.join(hit_examples)}\n"
        f"  미커버 예시: {', '.join(miss[:10])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
