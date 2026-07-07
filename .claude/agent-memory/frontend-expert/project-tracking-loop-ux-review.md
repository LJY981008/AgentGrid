---
name: project-tracking-loop-ux-review
description: 2026-07-07 추적·보정 루프 PWA UX 리뷰 — REVISE-GO. 블로킹 4건(거래 정정 경로·티커 자유입력·UnvalidatedWarning·close 가격 신선도 게이트)
metadata:
  type: project
---

2026-07-07 추적·보정 루프(portfolio_round/trade, routes/tracking.py, PWA '추적' 화면) 설계의 프론트 UX 리뷰 결과 = **REVISE-GO**.

**Why:** validated 룰 0개 상태에서 알파가 아닌 운용 규율·실측 피드백 축. 거래 기록이 루프 전체의 진실원본이라 입력 오류·조용한 왜곡 방지가 최우선.

**How to apply:** 구현 시 블로킹 4건 반영 확인 — ① trade 수정/삭제 API(활성 라운드 한정, close 후 불변 유지) ② 티커는 자유 텍스트 금지·선택형(Top5+보유 포지션)+서버 stock 마스터 검증 ③ 추적 화면에도 UnvalidatedWarning 상시(webapp-conventions BLOCKING) ④ close 시 가격 기준일 신선도 게이트(stale 이면 동결 거부/명시 확인). 개선안: 거래입력은 별도 시트/라우트+확인 단계(프리필 대신 '최근 종가 참고 표시+탭하여 채우기'), 4계열은 % 공통 단위 테이블+실보유만 $ 병기+파생 델타 2개(수동압축가치·vs SPY), 연환산 금지, 회고는 성과 프리뷰 먼저 보여준 2단계+임시저장. nav 6탭 허용. SW 는 /api NetworkOnly 명시. SPY 는 수집 유니버스에 실측 부재(2026-07-07 grep) — 수집 추가 선행 필요.
