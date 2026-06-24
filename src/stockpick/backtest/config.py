"""백테스트 설정 + 멱등 fingerprint. 전 필드 Decimal/int/date/str/bool — float 금지(재현성)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Final

# A1p2 L4: per-ticker 수익률 **상한 캡**(데이터 보기 전 동결·과적합 금지). sentinel 정제(L1~L3)를
# 뚫은 잔존 garbage·극소 진입가 폭발을 per-bar 수익률에서 차단. ret=exit/entry-1 은 entry>0·
# exit>=0 이라 ret>=-1(하한 폭발 불가) — 상한만 캡(하한 floor 는 정상 손실 마스킹=낙관편향).
#   CAP=+19.0 — 실재 16.2x 급등(GME, ret=15.2) 보존하며 199999배(sentinel exit) 폭발만 차단.
# 환경변수로 실험 조정 가능. cap 은 룰 정체성에 포함(compute_rule_signature) — 비정규 cap 으로
# 게이트 통과해도 signature 불일치라 validated flip 안 됨(동결 우회 차단).
_DEFAULT_RETURN_CAP: Final = Decimal(os.environ.get("STOCKPICK_RETURN_CAP", "19.0"))


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

    def __post_init__(self) -> None:
        # cap<=0 은 모든 수익을 음수로 뭉갬 = 백테스트 무의미. 조용한 오설정 금지(명시 실패).
        if self.period_return_cap <= 0:
            msg = f"period_return_cap 은 양수여야 함(현재 {self.period_return_cap})"
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
