# harness-auditor 메모리

- 2026-06-12 초기 감사 완료: 3축(정합성/버전/훅 로직) — 지적 전건 수정됨 (commit-msg -am 우회, rm 구분자 우회, drift 부분매칭 오탐, compose 매핑 사문화)
- 훅 회귀 테스트: `.claude/hooks/tests/run.sh` (19케이스) — 훅 수정 시 케이스 추가 의무
- 알려진 한계 (재지적 금지): pre-bash-guard 는 bash -c 래핑 못 잡음(정규식 한계, deny 와 이중방어 전제), git 차단 전무는 사용자 정책, settings.json `if` 필드는 공식 표준(2026-06 문서 확인)
- 버전 신선도 대조 대상: build.gradle / package.json / compose.yaml / gradle-wrapper.properties ↔ CLAUDE.md 3종·README
