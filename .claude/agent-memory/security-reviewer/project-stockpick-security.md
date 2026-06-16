---
name: project-stockpick-security
description: stockpick 보안 위협 모델 — 개인 1인용 한국/미국 주식 분석 도구, 실질 리스크 축
metadata:
  type: project
---

stockpick 은 개인 1인용 투자 분석 도구(공개 서비스 아님) — 위협 표면이 작다. 과도한 위협 모델링 대신 실질 리스크에 집중.

**실질 보안 축** (2026-06-16 M1 데이터 파이프라인 리뷰 기준):
- 시크릿: TIINGO_API_KEY / EODHD_API_KEY (그리고 기획상 KRX_API_KEY·KIS_APP_KEY/SECRET). `.env` gitignore 됨·git 추적 안 됨·히스토리 클린·`.env.example` 은 빈 템플릿(값 없음) — 위생 양호.
- 공급망: 런타임 deps 최소(duckdb·httpx·pyarrow). 표면 작음.
- 역직렬화: pickle/eval/yaml.load 없음. parquet 은 자체 수집분만 로드 → 낮음.
- 금융 BLOCKING(돈 걸림)이 보안만큼 중요: 생존편향(폐지 포함)·룩어헤드(t≤t)·수정주가 통일·Decimal(float 금지)·재현성.

**Why:** CLAUDE.md 가 security-reviewer 를 "개인용이라 경량"으로 규정. 금융 BLOCKING 은 stock-1st_plan §4.1 근거.
**How to apply:** SSRF·인증·XSS 같은 공개서비스 위협은 M4 웹앱 전까지 과하게 경고하지 말 것. 시크릿 노출 경로와 금융 무결성에 화력 집중.
관련: [[project-data-adapter-security]]
