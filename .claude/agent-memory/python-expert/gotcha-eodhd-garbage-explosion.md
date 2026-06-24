---
name: gotcha-eodhd-garbage-explosion
description: S6-b G-3 e80 발산 근원 = tiny-denominator × garbage-sentinel forward-return 폭발. 데이터drop 불충분·수익률 캡 필수. legit 천장=GME 16.2x
metadata:
  type: project
---

S6-b 게이트 G-3 oos_excess -10^80 발산의 근원과 정밀 임계 (2026-06-24 cache.duckdb 98.6M 행 실측).

**근원**: 벤치·엔진 `_holding_period_return` 의 per-종목 `ret=exit_p/entry_p-1`. EODHD garbage 가 두 형태로 폭발:
- 분자 garbage: forward adjusted 가 round sentinel($10k~$1M·$225k 등). 78%가 ≈$1M.
- 분모 tiny: entry adjusted 가 $0.0001 등 sub-cent(adj>0 이라 엔진 `entry_p<=0` 가드 통과). adj<0.001 = 2.997M행·0.001~0.01 = 2.715M행. 예 ZYRXD $0.0001→$225,000 = 2.25 billion x.

**데이터 drop(#1 adj<400k sentinel + #2 adj_factor<10k) 단독 불충분**: post-clean 후에도 max 2.25B x·163,164행이 17x 초과 잔존. sentinel 이 모든 magnitude($9k·$50k·$225k)에 산재 + tiny 분모는 가격밴드로 못 잡음.

**legit 천장(ground truth)**: 21거래일 forward 최대 수익률 — GME 2021 스퀴즈 **16.2x(+1625%)**(연속·문서화된 진짜 squeeze $5→$86), AMC 6.9x, PLUG/MARA 4.1x, NVDA 2.0x. 17x 초과는 전부 garbage(84% entry<$1·잔여 round sentinel·`*D` 폐지 placeholder FFPPD $10→$510).

**권고 캡 K**: per-종목 기간수익률을 **[-0.95, +19.0]** (즉 +1900%) 로 winsorize. GME 16.2x 보존(legit BLOCKING)·19x 초과 garbage 차단. 하한 -0.95 는 폐지청산(recovery)·정상 낙폭 보존. ⚠️ 캡=결과 변경(BLOCKING) → 정직 caveat 필수. 캡은 데이터정제 후에도 **필수 안전망**(중복 아님 — drop 이 못 잡는 tiny-denominator 커버).

**캡 위치**: per-종목 `ret` 계산 직후(`total += w*ret` 전), engine.py·benchmark.py 공유 `_holding_period_return` 단일 지점. 포트 pret 아님(개별 종목 폭발이 가중합 오염). config.py 에 `period_return_cap: Decimal`(fingerprint 포함·재현성). 룩어헤드 없음(시점 t 내 exit/entry 만).
