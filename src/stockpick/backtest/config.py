"""백테스트 설정 + 멱등 fingerprint. 전 필드 Decimal/int/date/str/bool — float 금지(재현성)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal


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
    trading_days_per_year: int = 252  # 연환산 상수(명시)

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
