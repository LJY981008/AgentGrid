---
name: project-tracking-loop-v1
description: 추적·보정 루프(월 라운드) v1 설계 — 사용자 비준 4건 + 2026-07-07 검토 REVISE-GO 판정·블로킹 3건
metadata:
  type: project
---

2026-07-07 기준, stock-1st_plan §5(추적·보정 루프)의 v1 설계가 진행 중. **사용자 비준 4건**: ① 라운드 단위 기록('2026-07' 라운드 = Top20 스냅샷+토의메모+Top5+거래+회고, 보유 이월 가능) ② PWA 폼 수동 거래입력(증권사 API 비목표) ③ 벤치 = SPY + Top20 등가중 ④ 구조화 회고(룰 가중치 보정 테이블은 validated 룰 생긴 뒤 v2).

**Why:** validated 룰 0개(momentum·momentum×ROE 게이트 FAIL) 상태에서 루프의 목적은 알파가 아니라 운용 규율·실측 피드백. 실측상 강한 기준선 = 유동성 필터 통과 등가중.

**How to apply:** 후속 기획 시 product-planner 검토 판정(REVISE-GO) 블로킹 3건을 선결로 취급 — (1) 이월 포지션 회계 규칙 미정의(라운드 경계 수익률 정의 불능) (2) 시드 Top20이 G-7 무결성 FAIL 데이터 산출물임을 스냅샷·화면에 동결 표기(validated=false 표기만으론 부족) (3) 4계열 척도(총수익/배당/adj) 통일 + SPY는 Common Stock 유니버스 밖(실측: universe.py ETF 미수집)이라 수집 경로 확정 필요. 신규 기획 문서는 버전 넘버링 추가(기준선 덮어쓰기 금지)·PLAN_STATUS 동기.
