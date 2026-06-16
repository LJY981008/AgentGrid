---
name: research-eodhd-insider-transactions
description: EODHD Insider Transactions (SEC Form 4) API 실측 — 신규 form4 엔드포인트 vs obsolete 레거시, 파라미터·필드·플랜 (2026-06-16)
metadata:
  type: reference
---

EODHD Insider Transactions API (SEC Form 4) — 공식 문서 실측 (2026-06-16, r.jina.ai + eodhd.com 직접 3회 교차검증).
출처: https://eodhd.com/financial-apis/insider-transactions-api

- **신규(권장) 엔드포인트**: `GET https://eodhd.com/api/sec-filings/{symbol}/form4`
  - path: symbol (US 티커, AAPL 또는 AAPL.US, .US 옵션, 대소문자 무관)
  - query: api_token(필수), page[offset](기본0), page[limit](기본20, 1~100)
  - 응답: data[](filing) + meta(total, page) + links(next만 제공 — 특정 페이지는 offset 증가로 도달)
  - filing: accession_number, filed_at, period_of_report, non_derivative[], derivative[], footnotes[]
  - 중첩 트랜잭션 스키마 풍부(reporting_owner_*, transaction_code, acquired_or_disposed, shares_amount 등)
- **레거시(obsolete) 엔드포인트**: `GET /api/insider-transactions` (code/from/to/limit/fmt 파라미터)
  - 문서가 "obsolete"로 명시, 신규 form4 권장
  - 응답 필드명은 텍스트로 미기재(스크린샷 이미지only) — 코드 참조 부적합
  - 트랜잭션 코드 P(매수)/S(매도)만 노출
- 콜 소비: **요청당 10 API calls**
- 플랜: **All-In-One + Fundamentals Data Feed**
- 커버리지: US 상장 Form 4 제출사만, SEC EDGAR 직접 소싱 일간 갱신, 티커별 이력 5~11년
- ⚠️ stockpick(KRX) 직접 무관 — 미국주식 한정. [[research-eodhd]] 계열 미국 데이터 연구의 일부
