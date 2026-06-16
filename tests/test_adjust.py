"""공유 헬퍼(_adjust.compute_adj_factor) 단위 테스트 — 순수 함수(라이브·IO 0).

검증 항목(수정주가 BLOCKING — 돈 걸림):
- 정상: adjusted==raw → 1 / 분할비 12자리 quantize 정확값 / 13자리 무한소수 ROUND_HALF_EVEN 경계
- 경계 방어(무수정 1 + WARNING, 조용한 왜곡 금지): adjusted=None / raw=0 / raw<0 / adjusted<=0
- WARNING 레코드에 ticker·date 포함(추적 가능)
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

import pytest

from stockpick.data._adjust import ADJ_FACTOR_DECIMAL_PLACES, compute_adj_factor

_TICKER = "AAPL"
_DATE = date(2020, 8, 28)


def _call(adjusted: Decimal | None, raw: Decimal) -> Decimal:
    return compute_adj_factor(adjusted, raw, source="tiingo", ticker=_TICKER, trade_date=_DATE)


def test_factor_one_when_adjusted_equals_raw() -> None:
    """무분할·무배당 구간: adjusted==raw → 정확히 1."""
    assert _call(Decimal("129.04"), Decimal("129.04")) == Decimal("1")


def test_split_factor_quantized_to_12_places() -> None:
    """분할비 12자리 quantize 정확값 — 헬퍼가 산출 단계에서 정밀도를 고정한다(저장 scale 정합)."""
    result = _call(Decimal("127.46"), Decimal("129.04"))
    expected = (Decimal("127.46") / Decimal("129.04")).quantize(
        Decimal("1E-12"), rounding=ROUND_HALF_EVEN
    )
    assert result == expected
    exponent = result.as_tuple().exponent  # 유한 Decimal → int
    assert isinstance(exponent, int)
    assert -exponent == ADJ_FACTOR_DECIMAL_PLACES == 12


def test_infinite_decimal_tail_rounds_half_even_at_13th_place() -> None:
    """13자리 이상 무한소수 꼬리는 ROUND_HALF_EVEN 으로 12자리에서 경계 반올림된다.

    1/3 = 0.3333...(무한) → 12자리에서 ...333(13째자리 3 < 5, 내림 유지). 산출값이 정확히
    Decimal('0.333333333333') 인지 고정(나눗셈 인공물 꼬리 제거 확인).
    """
    result = _call(Decimal("1"), Decimal("3"))
    assert result == Decimal("0.333333333333")
    # 2/3 = 0.6666...7 → 13째자리 6 >= 5 라 12째자리 올림(...667)
    result2 = _call(Decimal("2"), Decimal("3"))
    assert result2 == Decimal("0.666666666667")


def test_adjusted_none_returns_one_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """adjusted 결측(None) → 1 + WARNING(ticker·date 포함)."""
    with caplog.at_level(logging.WARNING):
        assert _call(None, Decimal("100")) == Decimal("1")
    rec = _only_warning(caplog)
    assert "결측" in rec.getMessage()
    _assert_ticker_date(rec)


def test_raw_zero_returns_one_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """raw=0(0 나눗셈 불가) → 1 + WARNING(ticker·date 포함)."""
    with caplog.at_level(logging.WARNING):
        assert _call(Decimal("100"), Decimal("0")) == Decimal("1")
    rec = _only_warning(caplog)
    assert "raw close<=0" in rec.getMessage()
    _assert_ticker_date(rec)


def test_raw_negative_returns_one_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """raw<0(음수 가격 불가) → 1 + WARNING(ticker·date 포함)."""
    with caplog.at_level(logging.WARNING):
        assert _call(Decimal("100"), Decimal("-50")) == Decimal("1")
    rec = _only_warning(caplog)
    assert "raw close<=0" in rec.getMessage()
    _assert_ticker_date(rec)


def test_adjusted_nonpositive_returns_one_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """⭐ 양수성 게이트 1차 방어선(A): adjusted<=0 → 음수/0 계수 방지, 1 + WARNING.

    실측 결함: compute_adj_factor(-50, 100) 은 -0.5(음수 계수)를 산출했었다 — 이후 수정주가가 부호
    반전·붕괴. raw>0 이라 raw 가드는 통과하므로 adjusted<=0 분기가 별도로 필요하다.
    """
    with caplog.at_level(logging.WARNING):
        assert _call(Decimal("-50"), Decimal("100")) == Decimal("1")  # raw>0, adjusted<0
    rec = _only_warning(caplog)
    assert "adjusted(수정종가)<=0" in rec.getMessage()
    _assert_ticker_date(rec)
    # adjusted=0 도 동일 차단
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        assert _call(Decimal("0"), Decimal("100")) == Decimal("1")
    assert "adjusted(수정종가)<=0" in _only_warning(caplog).getMessage()


def _only_warning(caplog: pytest.LogCaptureFixture) -> logging.LogRecord:
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, f"WARNING 1건 기대, 실제 {len(warnings)}"
    return warnings[0]


def _assert_ticker_date(rec: logging.LogRecord) -> None:
    msg = rec.getMessage()
    assert _TICKER in msg
    assert str(_DATE) in msg
