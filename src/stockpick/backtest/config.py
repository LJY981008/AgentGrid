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
