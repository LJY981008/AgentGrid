---
name: eodhd-adjfactor-threshold
description: EODHD adj_factor 임계 정밀 — legit 역분할 상한·adj_factor 단독 임계 위험·결합조건 검증 실측 (2026-06-24)
metadata:
  type: project
---

# adj_factor 임계 정밀 (legit 역분할 vs garbage) — cache.duckdb daily_bar 99.6M행 실측

대상: `data/parquet/cache.duckdb` daily_bar(ticker,trade_date,close,adj_factor). adjusted=close*adj_factor.
관련: [[eodhd-sentinel-1m-drop]] (sentinel $1M drop). 핫패스 benchmark.py·engine._holding_period_return.

**Why:** S6-b G-3 oos_excess -1e80 수치폭발 근원=EODHD garbage 수정주가. adj_factor 임계로 garbage drop 시 legit 역분할 오제거 위험 검증 필요.
**How to apply:** 정제 규칙 임계 확정 시 — adj_factor 단독 임계 금지(legit 오제거), 결합/근원 신호 사용.

## 핵심 실측 결론

1. **정분할주(AAPL/TSLA/NVDA/AMZN/MSFT)는 adj_factor ≤ 1.0** (과거가 낮춤). adj_factor>1 = 역분할 또는 garbage.
2. **legit 단일 역분할 상한 ~수십**: Citi C(1:10)=7.35, AIG(1:20)=12.41, GE(1:8)=4.87.
3. **legit 거듭 역분할(상폐회피 바이오)은 adj_factor 수천~3만까지 정상**: XSPA=12000(adjusted $33,720 legit 검증·연속 step·일간비율 max 2.59), IDRA=5434, IBIO=5000. 순수legit집합(close_min>=0.1·sentinel無 31,580종목) adj_f p99=100·p99.9=2700·max=29,081.
4. **⛔ adj_factor 단독 임계 위험**: adj_factor=5e7인데 adjusted sane($0.1~5000)인 행 8500만개. adj_factor 크다고 garbage 아님(legit 거듭역분할·페니 정상조정 공존).
5. **거대 adj_factor의 근원 = sentinel adjusted_close($1M) ÷ close**: close가 페니floor(0.0001)든 $1+든 adjusted_close=999999.9999 sentinel 만들려 adj_factor 폭발. 마커값 adj_factor=9999999999(1e10) 22,912행/50종목·>=1e9 56,484행/105종목 = 물리불가 인위값.
6. **garbage 판별 신호(legit 안전)**:
   - close<=0.0005 (페니floor): legit(C/AIG/GE/XSPA/IDRA/IBIO/BRK-A) 전부 0행 미검출 — 안전. 3,206,521행(3.2%).
   - round(adjusted,2)=1,000,000.00 sentinel: 732,989행(78%·[[eodhd-sentinel-1m-drop]]).
7. **⛔ 결합규칙 (adj_factor>1000 AND adjusted>=10000) = legit 오제거**: XSPA 1094행·IDRA 431·IBIO 262 잡힘(전부 legit 거듭역분할). 채택 금지.
8. **단일 신호 완벽분리 불가**: 일간 점프비율도 legit(XSPA 2.59·IDRA 4.47) vs garbage 겹침 — ATDS(uniform flat garbage)=10.0·RCAT 6.2로 legit과 근접. sentinel 점프형(ICCT 1867·CONC 30)만 큼. flat garbage(adj_f uniform·ATDS류)는 일간점프 미검출. **레이어 결합 필수**.

## 권고 임계 (데이터 근거)
- 1차: round(adjusted,2)=1000000.00 행drop (sentinel·legit 무손실).
- 2차: close<=0.0005 페니floor 행drop (legit 0 오제거·flat garbage ATDS류 포착).
- 3차 안전망: 기간수익률 winsorize 엔진/벤치 캡(legit 거듭역분할 보존하며 잔여 점프 차단).
- ❌ adj_factor 단독 임계·(adj_factor AND adjusted) 결합 = legit 거듭역분할 오제거로 금지.
- 종목단위 drop 금지(생존편향) — 항상 행단위.
