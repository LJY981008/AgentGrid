---
description: Web app (PWA) conventions for stockpick frontend. Personal 1-user dashboard - Top20/Top5 view, portfolio tracking, rule/backtest results. Mobile-first responsive PWA, server API consumed read-mostly. Loaded on webapp edits. Trigger phrases - 웹앱·프론트·화면·대시보드·PWA 작성 시.
paths: ["webapp/**"]
---

# Web App (PWA) Conventions — 초안 (M4 구현, 경로 예약)

> ⚠️ 웹앱은 M4 마일스톤. 지금은 경로(`webapp/`)·원칙만 예약. 프레임워크 확정은 M4 착수 시 frontend-expert 와 결정(미해결).

## 방향 (stock-1st_plan §7)

- **개인 1인용 대시보드** — Top20/Top5 뷰, 분산투자 현황·수익률, 추적 기록, 룰 버전·백테스트 결과
- **모바일 우선 반응형 + PWA** (홈 화면 추가, 앱처럼). Android 네이티브 폐기 결정(§3-2)
- 서버(Python API)를 소비하는 **읽기 위주** — 실거래·주문 없음(비목표)

## 원칙 (프레임워크 무관 — 확정 전 공통)

- 데이터는 서버 API(`/api/...`)에서. 프론트에 투자 로직(랭킹·점수) 중복 금지 — 서버가 단일 진실
- 차트는 라이브러리 선택 M4 (경량 우선). 숫자는 반올림·통화 포맷 일관
- API 베이스 URL·키는 env. 하드코딩 금지
- **사용자(백엔드 전문, 프론트 비전문)** — 결정은 백엔드 비유로 설명, 단순 구조 우선

## 사용자를 위한 메모

- PWA = 웹인데 폰 홈에 설치돼 앱처럼 뜨는 것. 별도 앱스토어 배포·네이티브 빌드 불필요 — 1인 유지보수 최선
