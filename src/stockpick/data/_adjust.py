"""수정계수(adj_factor) 산출 공유 헬퍼 — Tiingo·EODHD 어댑터가 재사용(TASK-C).

도메인 계약(`..types.DailyBar`)의 수정주가 모델은 **원본 불변 + adjusted = raw * adj_factor**
(원주가는 절대 변형 안 함). 두 소스 모두 "원시 종가(raw close)"와 "수정 종가(adjusted/adjClose)"를
별도로 주므로, 우리가 보관할 누적조정계수는

    adj_factor = adjusted_close / raw_close

이다(adjusted = raw * adj_factor 를 만족 → 곱하면 adjusted_close 복원). ⚠️ EODHD 명세 caveat 은
"(raw close / adjusted_close) 로 역산"이라 표현하나 그건 **역수(raw→adjusted 로 나눌 때의 제수)**
관점이며, 우리 계약의 adj_factor(=adjusted/raw, 곱셈자)와는 분자/분모가 뒤집힌 것이다. 계약 불변식
(adjusted = raw * adj_factor)을 유지하려면 분자=adjusted, 분모=raw 가 맞다(Tiingo adjClose/close
와 동일식).

⚠️ 정밀도 통제(TASK-C — storage.py 의 scale 37 밴드에이드 근본 해소): adjusted/raw 나눗셈은
기본 Decimal(prec=28) 연산이라 의미 없는 무한소수 꼬리를 만든다(소스의 adjusted·close 는 보통 소수
2~4자리뿐 — 28자리 꼬리는 나눗셈 인공물이지 의미정밀도가 아니다). 이를 저장층까지 흘리면 컬럼
scale 을 과도하게(37) 잡아야 했다. 여기서 **의도된 정밀도(소수 12자리)로 quantize** 해 산출
단계에서 고정한다.

왜 12자리인가(근거):
- adj_factor 는 가격에 곱해 수정주가를 만드는 **비율**이다. 가격 유효숫자가 ~6자리(예: 1209.98)인데
  factor 를 소수 12자리까지 보존하면, factor 가 1e-3 수준(대규모 분할 누적)이어도 유효숫자 9자리
  이상이 남아 가격 정밀도를 충분히 상회한다(반올림 오차가 가격 정밀도보다 훨씬 작음).
- 분할 비율(0.25, 0.1, 0.333333333333 등)·배당 누적조정을 충분히 표현한다.
- 12자리 고정 → 저장층 decimal128 컬럼 scale 을 37 → 12 로 축소할 수 있다(정수부 26자리 여유 —
  역분할로 factor 가 한·두 자릿수여도 수용).

경계(BLOCKING — 조용한 왜곡 방지): adjusted 결측 또는 raw<=0 이면 수정 불가 → 무수정(Decimal("1"))로
두고 WARNING. 정상 케이스에서 adjusted==raw 면 factor==1(무분할·무배당 구간).
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)

# adj_factor 의도 정밀도 = 소수 12자리(위 docstring 근거). 저장층 _FACTOR_SCALE 과 동일해야 한다
# (어댑터가 quantize 한 scale = 컬럼 scale → PrecisionError 없이 손실 없이 적재).
ADJ_FACTOR_DECIMAL_PLACES: Final = 12
_QUANTUM: Final = Decimal(1).scaleb(-ADJ_FACTOR_DECIMAL_PLACES)  # Decimal('1E-12')
_NO_ADJUST: Final = Decimal("1")


def compute_adj_factor(
    adjusted: Decimal | None,
    raw: Decimal,
    *,
    source: str,
    ticker: str,
    trade_date: date,
) -> Decimal:
    """adj_factor = quantize(adjusted / raw, 소수 12자리). 경계 시 무수정(1) + WARNING.

    adjusted = 소스의 수정종가(Tiingo adjClose / EODHD adjusted_close), raw = 소스의 원시 종가.
    계약 불변식: adjusted_close == raw_close * adj_factor (원본 불변). 나눗셈 무한소수 꼬리는 의도
    정밀도(12자리)로 quantize 해 산출 단계에서 고정한다(저장층 scale 과 정합 — TASK-C).

    경계 방어(조용한 왜곡 금지):
      - adjusted 결측(None) → 수정 불가, 1 적용 + WARNING
      - raw<=0(0 나눗셈·음수가 불가) → 1 적용 + WARNING

    source 는 로그 분류용(어느 소스의 어느 종목·날짜인지 추적). 키 등 민감정보는 인자에 없음.
    """
    if adjusted is None:
        logger.warning(
            "%s adjusted(수정종가) 결측 — adj_factor=1 적용: ticker=%s, date=%s",
            source,
            ticker,
            trade_date,
        )
        return _NO_ADJUST
    if raw <= 0:
        logger.warning(
            "%s raw close<=0 — adj_factor 산출 불가, 1 적용: ticker=%s, date=%s, raw=%s",
            source,
            ticker,
            trade_date,
            raw,
        )
        return _NO_ADJUST
    return (adjusted / raw).quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
