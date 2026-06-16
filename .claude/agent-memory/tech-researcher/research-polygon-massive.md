---
name: research-polygon-massive
description: Polygon.io(2025-10-30 Massive.com 리브랜딩) 미국주식 데이터 실측 — 가격·생존편향·수정주가 함정·⚠️해지후 삭제의무(재현성 탈락)
metadata:
  type: project
---

# Polygon.io → Massive.com 미국주식 데이터소스 실측 (재확인 2026-06-16)

**리브랜딩**: 2025-10-30 polygon.io → massive.com 공식 개명. api.polygon.io 엔드포인트·계정·키 호환 유지. 공식 도메인 massive.com (문서/가격/blog SPA — WebFetch 제목만 렌더, **r.jina.ai 우회** 필요).

**Why:** stockpick 도메인 한국→미국 전환, 사용자 Polygon 후보 지목. 가격전용·EOD 요건.
**How to apply:** 미국 데이터소스 추천 시 기준. 가격은 2026-06 실측 — 6개월+ 경과 시 massive.com/pricing 재확인.

## 가격 (2026-06 실측, 월·STOCKS 한정) — 메모리/현행 일치
- Basic(Free): $0 / 5 calls/min / EOD / 2년 / flat files 미포함
- Starter: $29 / unlimited / 15분지연 / 5년 / flat files 포함
- Developer: $79 / unlimited / 15분지연 / 10년 / flat files 포함
- Advanced: $199 / unlimited / 실시간 / 20+년 / flat files 포함
- 연납 20% 할인. flat files(S3)는 전 유료플랜 포함(Free 제외).
- 가격전용 요건엔 Starter($29, 5년) 또는 Developer($79, 10년)면 충분 — EDGAR가 재무 담당.

## 우리 BLOCKING 항목
- ⭐생존편향: 우수. Tickers 엔드포인트 active=false → 폐지종목, delisted_utc("마지막 거래일") 필드. EOD tick history 2004~ (30년 미달).
- ⚠️수정주가 **함정 재확인(2026-06)**: KB 공식 "adjusted for splits, but not dividends". aggregates adjusted=true=split만, 배당 미반영. adjusted=false=split도 미조정.
- ⭐배당조정 개선: 2026-02-18 splits/dividends 엔드포인트 출시(전 플랜). historical_adjustment_factor 제공 → 수동 배당조정 가능. but aggregates 네이티브 배당조정은 "추후". split_adjusted_cash_amount 도 제공.
- ⚠️flat files는 **unadjusted prices만** 제공(split 조정도 안 됨). 조정은 REST 별도호출 or 직접계산. (stonkscapital 보고)
- PIT재무: Financials API 있으나 SEC 파생·표준화 한계 → stockpick은 [[research-sec-edgar-free-financials]] EDGAR 직접이 더 나음.

## ⚠️재현성 BLOCKING — 해지 후 삭제 의무 (SimFin과 동일 탈락 사유)
- **Market Data Terms(massive.com/terms/market_data_terms.pdf)**: "if the Agreement or your account are terminated... you agree to cease all use of the Market Data and **delete all Market Data in your possession**."
- "Market Data is strictly for **display use only**", 복제·저장·재배포·mirroring 금지.
- Individuals ToS §8.4: termination 시 "the license and any other rights... will end". 생존 조항 없음.
- → 구독 유지하는 동안만 합법 보유. **해지 후 다운로드 데이터 보유 불가 = 재현성 핵심 탈락** (cf. [[research-simfin]] 동일). [[research-us-data-sources]] Sharadar/Norgate 등 보유허용 소스가 재현성 우위.
- 재배포: 개인티어 불가, business 제품 가입 필요.

## 품질 보고 (리브랜딩 후)
- stonkscapital "Massive Problems" 시리즈: DB에 **가짜 split 존재**("some splits aren't real, you have to figure out which are legit"), late prints(백테스트 오염). corporate actions 교차검증 필수.
- 2026-02 changelog: 복합 corporate action(배당+역분할/동일일자 다중)에서 split-adjusted dividend cash 오류 → 수정됨.

## Caveat
- 30년 요건 미충족(최대 20+년, tick 2004~). 한국 plan "30년"을 미국 전환 시 재정의 필요.
- Linux/Python: REST + boto3(S3 flat files) — 데스크톱 종속 없음, DuckDB 스택 정합. but 위 삭제의무로 영구보관 불가.
