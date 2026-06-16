---
name: project-domain-pivot
description: 프로젝트 도메인 = 개인 투자용 한국주식 주가분석(stockpick), 서버 Python. 2026-06-16 MCP 신뢰성 레지스트리에서 전환 완료.
metadata:
  type: project
---

도메인 = **개인 투자용 한국 주식(코스피/코스닥) 주가 분석 프로그램 (stockpick)**, 서버 스택 **Python 3.12+**. 2026-06-16 기존 "MCP/AI에이전트 신뢰성 레지스트리"(Java/Spring Boot 4.1, Testcontainers, Next 16)에서 in-place 전환 완료.

**Why:** 사용자가 도메인 전환 선언, 구 컨텍스트 전부 폐기 지시.

**How to apply:** 모든 리서치는 한국주식/Python 생태계 기준. 구 Boot4/Next16 스택 리서치(`docs/research/2026-06-12-*`)와 옛 plan(`1st/2nd/3rd_plan.md`)은 폐기 — 인용 금지. 데이터소스 리서치는 `docs/research/2026-06-16-한국주식-데이터소스.md` 참조(중복 방지). 현 기준선 기획 = `docs/plans/stock-1st_plan.md`.
