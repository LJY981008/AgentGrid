# 구현 히스토리 인덱스

> 모든 구현 작업(플랜모드/일반 불문)의 의도·계획·전후 비교 기록.
> 규약: 코드(src) 변경 커밋에는 이 디렉토리의 엔트리가 동반되어야 함 — harness-drift-check 가 물리 강제.
> 새 엔트리: `docs/templates/work-history-template.md` 복사 → `{YYYY-MM-DD}-{작업명}.md` → 아래 표에 행 추가.

| 날짜 | 작업 | 유형 | 엔트리 |
|---|---|---|---|
| 2026-06-12 | work-history 체계 도입 | 하네스/인프라 | [[2026-06-12-work-history-체계-도입]] |
| 2026-06-12 | 프론트 목업 4화면 (와이어프레임 대용) | 일반 구현 | [[2026-06-12-프론트-목업-4화면]] |
| 2026-06-16 | M0 — 도메인·스택 전환 (MCP→한국주식, Java/Next→Python/PWA) | 하네스/인프라 | [[2026-06-16-M0-스택전환]] |
| 2026-06-16 | M1 S0-S1 — 결정 확정·계약 정밀도 교정(float→Decimal) | 일반 구현 | [[2026-06-16-M1-S0S1-결정·계약교정]] |
| 2026-06-16 | B-env — Docker 기반 uv 개발/실행 환경(Dockerfile·app 서비스·uv.lock) | 하네스/인프라 | [[2026-06-16-B-env-docker-uv]] |
| 2026-06-16 | B-contract — 미국 도메인 계약 재설계(CIK+ticker·Exchange·DataSource Protocol) | 일반 구현 | [[2026-06-16-B-contract-미국계약]] |
| 2026-06-16 | B-pipeline — Tiingo EOD 가격 어댑터(httpx·adj_factor·모킹 테스트, 라이브 0) | 일반 구현 | [[2026-06-16-B-pipeline-tiingo-어댑터]] |
