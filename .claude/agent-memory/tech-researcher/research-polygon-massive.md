---
name: research-polygon-massive
description: Polygon.io(2026 Massive.com 리브랜딩) 미국주식 데이터 실측 — 가격·생존편향·PIT재무·수정주가 함정
metadata:
  type: project
---

# Polygon.io → Massive.com 미국주식 데이터소스 실측 (2026-06-16)

**리브랜딩**: polygon.io 도메인이 massive.com 으로 301 리다이렉트. 공식 클라이언트 repo도 massive-com/client-python. polygon API 키/엔드포인트(api.polygon.io)는 당분간 호환. ([[research-data-source-api-surface]] 한국 데이터소스와 대비 — 미국 전환 후보)

**Why:** stockpick 도메인이 한국→미국 주식 주력 전환. 사용자가 Polygon 후보 지목.
**How to apply:** 미국 데이터소스 추천 시 이 실측 기준. 가격은 2026-06 기준 — 6개월+ 경과 시 massive.com/pricing 재확인.

## 가격 (2026-06, 월·미국주식 한정)
- Free(Basic): $0 / 5 calls/min / EOD + 2년 분봉 히스토리 / 15분 지연 / 폐지종목 포함(active=false)
- Starter: $29 / unlimited calls / 5년 / 15분 지연 / flat files 포함
- Developer: $79 / unlimited / 10년 / 15분 지연 + trades
- Advanced: $199 / unlimited / 20년+ / 실시간(tick)
- 연납 20% 할인. flat files(S3)는 **전 유료플랜 포함**.

## 우리 BLOCKING 항목 평가
- ⭐생존편향: 우수. Tickers 엔드포인트 active=false → 폐지종목, delisted_utc 필드. 무료에서도 가능.
- 수정주가 **함정**: aggregates `adjusted=true`는 **split만 조정, 배당 미반영**(공식 문서 명시). 배당조정가는 dividends 엔드포인트로 직접 계산 필요.
- 룩어헤드(PIT): Financials API가 SEC 10-K/10-Q 직접, filing_date 쿼리 지원 → point-in-time 가능. 다만 SEC 파생이라 커버리지·표준화 한계.
- history: tick 2004~, daily 더 김(20년+은 Advanced). 30년 미달.
- 재현성: flat files S3(boto3) 벌크 다운로드 → 로컬 Parquet 적재 가능, 우리 DuckDB 스택과 정합.

## Caveat
- Massive 리브랜딩 후 데이터 품질 비판(stonkscapital "Massive Problems"), 배당/split 누락 보고(SPY 등). 백테스트 전 corporate actions 교차검증 필수.
- 30년 요건 미충족(최대 20년+). 한국 stock-1st_plan의 "30년"을 미국 전환 시 재정의 필요.
