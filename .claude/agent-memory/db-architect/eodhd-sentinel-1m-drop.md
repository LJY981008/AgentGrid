---
name: eodhd-sentinel-1m-drop
description: EODHD $1M sentinel garbage 정밀 drop 술어 실측 — round(adjusted,2)=1000000.00, 행단위, legit 무손실 (2026-06-24)
metadata:
  type: project
---

EODHD 소스 garbage 중 **$1M sentinel** drop 정밀 술어 확정(cache.duckdb daily_bar 99.9M행 실측). adjusted = close*adj_factor (adj_factor=adjusted_close/raw_close, _adjust.compute_adj_factor).

**확정 술어 P1 (행 단위)**: `round(close*adj_factor,2) = 1000000.00`
- 732,989행 / 793종목 제거. B버킷 [999999,1000001] 총 734,563행 중 99.8%가 정확히 round=1000000.00 (압도적 단일 sentinel).
- 범위 술어 [999999,1000001]은 +1574행(인접 999999.xx 종목별 flat garbage)만 추가 — 과포함. **round 2자리 정확매치가 정밀**.

**legit 무손실 검증**:
- BRK-A: adj_factor=1.0, max adjusted=$809,350 → sentinel 미해당(절대 안 걸림). C버킷 [800k,999999) 진입도 sentinel 술어와 직교.
- P1 sentinel 행의 raw close 분포: 65% penny주(close<10), legit 고가주가 adjusted 정확히 $1,000,000.00 될 확률 ~0.

**⚠️ 행 단위 필수 (종목 drop 금지)**: 793종목 중 779종목이 *일부 시점만* sentinel(전시점 sentinel은 14종목). legit 시계열 중간에 sentinel 행이 점점이 박힘 → 종목 통째 drop 시 생존편향·legit 대량손실.

**P1 단독은 폭발종목 불완전 — 3겹 모두 필요**:
- GHGH: sentinel 168행 제거로 폭발 완전 해소(잔존 max adjusted $0.82 정상).
- ATDS: sentinel 5089행 + 잔존 1878행 adj_factor 99억 uniform garbage → P1 미포착, **adj_factor drop(2겹)이 별도로 잡아야**.
- raw close=999999.9999 sentinel 165,447행/312종목 중 64,697행은 adjusted≠$1M(per종목 flat garbage 645753.84 등) → P1 미포착. **close raw-sentinel 직교 술어 추가 권고**.
- sentinel drop 후에도 adjusted>=400k 잔존 211,171행/1001종목 → adj_factor 임계·수익률 winsorize 안전망 필요.

라운드 sentinel 전수: $1M(732,989) 압도적, 그 외 $100k/$900k/$250k/$500k/$200k/$120k/$300k/$600k 등은 수백~수천행(우연 가능성 혼재 — $1M처럼 단정 불가, winsorize/adj_factor가 커버).

핫패스: benchmark.py(equal_weight_universe·_holding_period_return 복리 e80 발산), storage.py(normalize_ohlc A-1·verify_parquet), clean_ohlc.py(A-1 migration). [[s5a-pg-schema-design]]
