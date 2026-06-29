"""IdentityResolver 구현체 — ticker→cik 해소(생존편향 앵커).

`EdgarSnapshotResolver`: `data.edgar` 가 저장한 **현재 스냅샷**(`base_dir/edgar/ticker_cik.json`)을
읽어 ticker→cik 를 해소한다. `on`(시점)은 무시 — 현재 매핑만(폐지·과거 티커 미수록). 결제 후
시점별 `TickerHistoryResolver`(SEC submissions 이력·생존편향 정답)가 같은 Protocol 로 추가되며,
그때 `on` 을 사용한다. 엔진·api 는 Protocol(`cik_for`)만 의존 → 구현 교체는 DI(코드 0 변경).

미해소 ticker(저장본에 없음·미적재) → 빈 문자열(조용한 추측 금지 — 기존 계약). 저장본 부재면 빈 맵
→ 전부 ""(현 동작 유지·에러 아님).

모듈 경계: `backtest` 는 `data`(저장본 읽기)·`..types` 만 의존. 라이브 SEC 호출 안 함(저장본만).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import TYPE_CHECKING

from ..data.edgar import load_ticker_cik

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# ticker_history.json 한 구간: (cik|None, valid_from, valid_to|None). valid_to=첫 무효일(배타 상한).
_HistoryRow = tuple["str | None", date, "date | None"]


class EdgarSnapshotResolver:
    """현재 ticker→cik 스냅샷 기반 IdentityResolver. 생성자에서 저장본 1회 로드(재read 없음)."""

    def __init__(self, base_dir: Path) -> None:
        self._map = load_ticker_cik(base_dir)
        logger.info("EdgarSnapshotResolver 로드: ticker→cik %d건", len(self._map))

    def cik_for(self, ticker: str, *, on: date) -> str:  # noqa: ARG002 (on=시점, 스냅샷은 무시)
        """ticker(대문자 정규화) → cik. 미해소면 "". `on` 무시(현재 스냅샷 — history 는 후속)."""
        return self._map.get(ticker.upper(), "")


def _load_ticker_history(base_dir: Path) -> dict[str, list[_HistoryRow]]:
    """`base_dir/ticker_history.json`(db.export_ticker_history_snapshot 산출) → ticker별 구간 맵.

    포맷 = `{generated_at, history:[{ticker, cik, valid_from, valid_to}]}`(stock_snapshot 동형
    경계 — 외부 입력이라 isinstance 로 Any 흐름 차단). 파일 부재→빈 맵(미실행 정상·에러 아님).
    """
    path = base_dir / "ticker_history.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    history: dict[str, list[_HistoryRow]] = {}
    for rec in payload["history"]:
        ticker = str(rec["ticker"]).upper()
        cik_raw = rec["cik"]
        cik = str(cik_raw) if isinstance(cik_raw, str) and cik_raw else None  # ""·null→None
        valid_from = date.fromisoformat(str(rec["valid_from"]))
        vt_raw = rec["valid_to"]
        valid_to = date.fromisoformat(str(vt_raw)) if isinstance(vt_raw, str) else None
        history.setdefault(ticker, []).append((cik, valid_from, valid_to))
    return history


class PitIdentityResolver:
    """시점별 ticker→cik(생존편향+룩어헤드 정답). `ticker_history.json` 1회 로드(핫패스 PG 회피).

    조회 = `valid_from≤on AND (valid_to None OR on<valid_to)`. **경계 `on<valid_to` 배제**(폐지
    마지막 실거래일 포함·경계날 배제 — MasterUniverse `delisted_at+1` 정렬). **다중매칭=raise**
    (중첩 윈도우 = 데이터 무결성 버그·스키마에 EXCLUDE 제약 없음 → resolver 가 유일 방어선·금융
    BLOCKING: 모호한 식별을 조용히 추측하지 않는다). 0매칭·cik None → "" (추측 금지). 파일 부재→
    빈 맵(EdgarSnapshotResolver 와 동일 폴백). 기존 EdgarSnapshotResolver 보존 — 이건 신규·DI 교체.
    """

    def __init__(self, base_dir: Path) -> None:
        self._history = _load_ticker_history(base_dir)
        spans = sum(len(v) for v in self._history.values())
        logger.info("PitIdentityResolver 로드: ticker %d개·구간 %d행", len(self._history), spans)

    def cik_for(self, ticker: str, *, on: date) -> str:
        """시점 on 에서 ticker 의 cik. 0매칭="" · 1매칭=cik(None→"") · 다중매칭=raise(BLOCKING)."""
        rows = self._history.get(ticker.upper(), [])
        matched = [
            cik
            for cik, valid_from, valid_to in rows
            if valid_from <= on and (valid_to is None or on < valid_to)
        ]
        if not matched:
            return ""
        if len(matched) > 1:
            msg = (
                f"ticker_history 다중매칭: ticker={ticker} on={on} {len(matched)}건 "
                "(중첩 윈도우 — 데이터 무결성 위반·모호한 cik 추측 금지)"
            )
            raise ValueError(msg)
        return matched[0] or ""
