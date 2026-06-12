# 🏠 Agent Grid 지식 베이스 (MOC)

> 옵시디언 볼트 루트. `docs/` 를 볼트로 열기. 새 문서 생성 시 [[#템플릿]] 사용 + 이 MOC 에 링크 추가
> (research/decisions 신규 문서는 harness-drift-check 가 HOME.md 동기화를 강제).

## 📋 기획 (plans/)

- [[plans/1st_plan|1차 기획안]] — 비전·핵심 가치·기술 스택 (기준 문서)
- [[plans/2nd_plan|2차 기획안]] — MVP 구체화: 신뢰성 지표 6축·기능 명세·마일스톤
- [[plans/3rd_plan|3차 기획안]] — 미해결 질문 5건 확정: 캘리브레이션·LLM(sonnet-4-6)·격리 2단계·rate limit·풀 4화면 → DB 스키마 착수 선언
- [[plans/PLAN_STATUS|기획 현황판]] — 문서 상태 + 미해결 질문 추적

## 🏛️ 아키텍처 결정 (decisions/)

> ADR 형식. 템플릿: [[templates/adr-template]]

- (아직 없음 — 첫 ADR 은 DB 스키마 설계 시점 예상)

## 🔬 리서치 (research/)

- [[research/2026-06-12-스택-버전-리서치|2026-06-12 스택 버전 리서치]] — Boot 4.1/Next 16/인프라/Claude Code 포맷 확정 근거

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
