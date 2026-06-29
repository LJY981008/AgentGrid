"""폐지 ticker→cik 복구(A1) — 생존편향-안전 재무 팩터의 전제.

SEC `company_tickers.json` 은 현재 신고사만 → 폐지종목 ticker→cik 매핑 부재. 단 cik 만 알면
companyfacts 가 폐지사의 과거 신고를 PIT-correct(filed≤t) 반환. 이 모듈이 폐지 ticker 의 cik 를
복구해 A2 PIT ticker_history 의 폐지행 입력을 만든다. **delisted_date 동반**(ticker 재사용 구분 —
같은 ticker 가 폐지 후 타사에 재할당될 수 있어 폐지일이 엔티티 식별 키).

cik 소스(주입): 1차 EODHD ID-Mapping(`EodhdSource.fetch_id_mapping`·Free 플랜 포함). 폐지 커버<80%면
SEC `cik-lookup-data.txt`(회사명 기반·후속). 미커버 ticker = 결과서 제외(카운트 로그·조용한 추측 금지).
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


def store_delisted_ciks(mapping: dict[str, tuple[str, date]], base_dir: Path) -> Path:
    """`{ticker:(cik,delisted_date)}` → `base_dir/edgar/delisted_cik.json`(사람 읽기·교차검증 가능).

    형식: `{ticker: {cik, delisted_date(ISO)}}`. EODHD 약관(해지 후 삭제)에도 cik 는 SEC 퍼블릭도메인
    이라 영구보관 합법(cik-lookup-data.txt 교차검증 전제). 반환=경로.
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
