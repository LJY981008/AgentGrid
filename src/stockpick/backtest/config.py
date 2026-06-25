"""백테스트 설정 + 멱등 fingerprint. 전 필드 Decimal/int/date/str/bool — float 금지(재현성)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Final

# 수익률 처리 — per-ticker simple return 상한 clip(ADR-010 동결·±100%/리밸). ret=exit/entry-1 은
# entry>0·exit>=0 이라 ret>=-1(하한 구조적) → 상한만 clip 하면 [-1,+1]. min(ret, cap).
#   CAP=+1.0(=+100%) — 표준 return clipping(±100%). A1p2 의 +19.0 은 Phase 0a 진단서 불충분 입증:
#   top-5 w=0.2 → 1 cap-hit 시 pret=0.2×19=+380%(equity ×4.8) 복리 폭발(cap-hit=ret≥+1900%/월=
#   정상 알파 아님). +1.0 clip 시 0.2×1=+20%(×1.2)로 증폭기 제거(root fix). decile(w↓)이 추가 완화.
# 환경변수 조정 가능. cap 은 룰 정체성(compute_rule_signature) 포함 — 비정규 cap 게이트는 flip 차단.
_DEFAULT_RETURN_CAP: Final = Decimal(os.environ.get("STOCKPICK_RETURN_CAP", "1.0"))

# PIT 유동성 유니버스 필터(ADR-010·게이트 전 동결·외부 시장원칙). raw close(t)≥floor + ADV20≥min_adv
# 인 종목만 거래가능 유니버스(시점별·생존편향 안전). microcap penny 분모붕괴·비현실 종목 배제.
#   PRICE=$5(SEC penny 정의·JT 2001) · ADV=$1M(20거래일 mean(close×volume)·하위 비유동 꼬리 제거)
#   WINDOW=20거래일. 시총하한은 0c(SEC shares ≈0%) 불가 → ADV 프록시 단독.
_DEFAULT_MIN_PRICE_FLOOR: Final = Decimal(os.environ.get("STOCKPICK_MIN_PRICE", "5"))
_DEFAULT_MIN_ADV_DOLLAR: Final = Decimal(os.environ.get("STOCKPICK_MIN_ADV", "1000000"))
_DEFAULT_ADV_WINDOW_DAYS: Final = int(os.environ.get("STOCKPICK_ADV_WINDOW", "20"))


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """단일 백테스트 실행의 모든 입력(같은 config = 같은 결과). float 필드 금지(0.1 비재현)."""

    strategy_name: str
    top_n: int
    lookback_days: int
    skip_recent_days: int
    rebalance_freq: str  # "monthly" | "quarterly"
    cost_bps: Decimal  # 진입·청산 회전분 bps(수수료+슬리피지)
    delisting_recovery_rate: Decimal  # [0,1] 폐지 시 entry 대비 회수 비율(0=휴지, 1=마지막가)
    group_by_exchange: bool
    start: date
    end: date
    trading_days_per_year: int = 252  # 연환산 상수(현재 metrics 미사용·예약 — 일별 sharpe 도입 시)
    period_return_cap: Decimal = _DEFAULT_RETURN_CAP  # L4 상한 캡(재현성 → fingerprint + rule_sig)
    # 유동성 PIT 필터(ADR-010·fingerprint + rule_sig 동결). 전부 양수.
    min_price_floor: Decimal = _DEFAULT_MIN_PRICE_FLOOR
    min_adv_dollar: Decimal = _DEFAULT_MIN_ADV_DOLLAR
    adv_window_days: int = _DEFAULT_ADV_WINDOW_DAYS

    def __post_init__(self) -> None:
        # 조용한 오설정 금지(명시 실패). cap<=0 은 모든 수익 음수 뭉갬·유동성 임계 음수=무의미.
        if self.period_return_cap <= 0:
            msg = f"period_return_cap 은 양수여야 함(현재 {self.period_return_cap})"
            raise ValueError(msg)
        if self.min_price_floor <= 0:
            msg = f"min_price_floor 는 양수여야 함(현재 {self.min_price_floor})"
            raise ValueError(msg)
        if self.min_adv_dollar <= 0:
            msg = f"min_adv_dollar 는 양수여야 함(현재 {self.min_adv_dollar})"
            raise ValueError(msg)
        if self.adv_window_days <= 0:
            msg = f"adv_window_days 는 양수여야 함(현재 {self.adv_window_days})"
            raise ValueError(msg)

    def fingerprint(self) -> str:
        """canonical 직렬화 → sha256. Decimal normalize·sort_keys 로 의미동일=해시동일."""
        return hashlib.sha256(
            json.dumps(_canonical(asdict(self)), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def _canonical(obj: object) -> object:
    """Decimal→normalize 문자열, date→ISO, dict 재귀. float 유입은 명시 실패(재현성 BLOCKING)."""
    if isinstance(obj, float):
        msg = f"BacktestConfig 에 float 금지(재현성): {obj!r}"
        raise TypeError(msg)
    if isinstance(obj, Decimal):
        return f"D:{obj.normalize():f}"
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in obj.items()}
    return obj
