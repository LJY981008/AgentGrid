---
name: project-domain-pivot
description: 2026-06-16 도메인 전면 전환 — MCP 신뢰성 레지스트리 폐기, 개인 1인용 한국 주식 주가분석으로 in-place 전환. 새 기준선 stock-1st_plan.md
metadata:
  type: project
---

2026-06-16 도메인 전면 전환 확정. 기존 `1st/2nd/3rd_plan.md`(MCP 신뢰성 레지스트리, 하이브리드 등급/제출 파이프라인 계열)는 **전부 폐기**. 새 도메인 = **개인 투자용 한국 주식 주가 분석 프로그램**. 새 기준선 = `docs/plans/stock-1st_plan.md`.

**확정 결정 5건 (변경 금지)**: ①레포 in-place 전환(하네스·git·볼트·work-history 골격 유지, 스택만 교체) ②서버=Python·프론트=PWA 웹앱(Android 폐기) ③정량 Top20→수동 Top5(Claude 세션 토의)→분산투자→추적·보정 루프 ④AI 자동화 현재 비구현·미래 여지만(데이터/Top 산출을 모듈 경계로) ⑤개인 1인용(멀티유저·자동매매·인증 비목표).

**Why:** 레지스트리는 1인 운영 부담·보안표면 과다, 본인이 사용자일 때 가치 미달. 주가분석은 본인=사용자·검증자로 피드백 루프 짧음.

**How to apply:** 후속 기획은 stock-1st_plan §3 5건을 기준선으로. 핵심 설계 원칙(BLOCKING): 백테스트 검증 필수, 생존편향(폐지종목 포함)·수정주가·룩어헤드 회피, LLM은 정성보정용이지 알파소스 아님. M1(데이터 신뢰성) 통과 없이 M2(백테스트) 금지. 미해결 8건은 §9 — 데이터소스(tech-researcher 조사중)·룰가중치·백테스트프레임워크(vectorbt/backtrader)·시계열DB(db-architect)·비중산정·갱신주기·거래비용·폐지종목 fallback. RabbitMQ/Outbox 잔존 여부는 §9-6에서 판단. 기존 [[project-open-questions-status]](MCP 레지스트리 미해결질문)는 폐기 — 참조 금지.
