# devops-engineer 메모리

- 현행 구성: compose.yaml profiles 3종(기본/monitoring/app), Dockerfile 2종(backend JRE21 multi-stage, frontend Next standalone), CI 3 job(backend full test·frontend·훅 회귀), Dependabot 주간 4 생태계
- 이미지 3중 일치 의무: compose.yaml ↔ TestcontainersConfiguration.java ↔ backend/CLAUDE.md
- Grafana 시드 대시보드: agentgrid-backend.json 7패널 (7번 RabbitMQ 패널은 도메인 코드 후 활성)
- prometheus.yml: host(bootRun)·container(profile app) 듀얼 타겟 — 하나 down 정상
- Grafana :3001 (frontend :3000 충돌 회피), admin/agentgrid-local
