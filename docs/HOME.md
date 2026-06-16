# 🏠 Agent Grid 지식 베이스 (MOC)

> 옵시디언 볼트 루트. `docs/` 를 볼트로 열기. 새 문서 생성 시 [[#템플릿]] 사용 + 이 MOC 에 링크 추가
> (research/decisions 신규 문서는 harness-drift-check 가 HOME.md 동기화를 강제).

## 📋 기획 (plans/)

> ⚠️ **2026-06-16 도메인 전환**: MCP 신뢰성 레지스트리 → 개인 투자용 한국 주식 분석. 아래 1st/2nd/3rd 는 폐기(보존만).

- [[plans/stock-1st_plan|한국주식 기준선]] — **현행** Top20 정량→수동 Top5→분산투자 추적·보정, Python+PWA, 미해결 8건
- [[plans/PLAN_STATUS|기획 현황판]] — 전환 선언 + 데이터소스 리서치 + 미해결 질문 추적
- ~~[[plans/1st_plan]] · [[plans/2nd_plan]] · [[plans/3rd_plan]]~~ — (구) MCP 레지스트리, 폐기

## 🏛️ 아키텍처 결정 (decisions/)

> ADR 형식. 템플릿: [[templates/adr-template]]

- (아직 없음 — 첫 ADR 은 DB 스키마 설계 시점 예상)

## 🔬 리서치 (research/)

- [[research/2026-06-16-한국주식-데이터소스|2026-06-16 한국주식 데이터소스]] — **현행** 벌크=FDR+pykrx / 일일=KRX OpenAPI / 저장=Parquet+PG, 생존편향·수정주가 caveat
- ~~[[research/2026-06-12-스택-버전-리서치]]~~ — (구) Boot 4.1/Next 16, 도메인 전환으로 폐기

## 🛠️ 구현 히스토리 (work-history/)

> 모든 구현의 의도·계획(플랜 백업)·전후 비교. 인덱스: [[work-history/INDEX]]
> 템플릿: [[templates/work-history-template]] — src 변경 커밋에 엔트리 동반 (drift 강제)

## 📓 개발 일지 (dev-log/)

> 템플릿: [[templates/devlog-template]] — 막힌 것·결정·다음 할 일 기록

- [[dev-log/2026-06-12|2026-06-12]] — 프로젝트 세팅 (하네스·스캐폴딩·깃·검증·기획 v2)

## 템플릿

- [[templates/adr-template]] — 아키텍처 결정 기록
- [[templates/devlog-template]] — 개발 일지
- [[templates/research-template]] — 리서치 노트

## 외부 참조

- 하네스 가이드: `/home/code/project/claude-setting/`
- 발전형 하네스 실전: `/home/code/project/tbbe-hub/.claude/`
- GitHub: https://github.com/LJY981008/AgentGrid
