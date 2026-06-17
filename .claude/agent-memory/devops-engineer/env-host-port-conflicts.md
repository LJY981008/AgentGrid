---
name: env-host-port-conflicts
description: 로컬 호스트 포트 5432·5173 은 타 프로젝트(AiCrawl)가 상시 점유 — stockpick compose 는 리맵 필수
metadata:
  type: project
---

stockpick compose 의 호스트 포트는 타 프로젝트와 충돌하므로 리맵해서 바인딩한다: postgres `127.0.0.1:5433:5432`, web `127.0.0.1:5174:5173`, app `127.0.0.1:8000:8000`(8000 은 free).

**Why:** 같은 머신의 다른 프로젝트가 호스트 포트를 상시 점유한다 (2026-06-17 실측: `aicrawl-postgres` 컨테이너가 0.0.0.0:5432, `AiCrawl/node_modules/.bin/vite` 가 127.0.0.1:5173). 호스트 5432/5173 을 그대로 쓰면 `docker compose up` 이 bind 충돌로 실패한다. 컨테이너 내부 포트(5432·5173·8000)는 불변이라 app DATABASE_URL(postgres:5432)·vite proxy 는 리맵 영향 없음.

**How to apply:** compose 에 호스트 publish 포트를 새로 추가/변경할 때, 먼저 `ss -ltnp | grep ':<port>'` 로 점유 확인. 점유 시 호스트측만 +1 리맵(컨테이너 내부는 유지). 모든 publish 는 외부망 차단 위해 `127.0.0.1:` 프리픽스(1인 로컬·인증 없음). web 의 vite proxy 대상은 컨테이너 네트워크 기준 `VITE_DEV_API_TARGET=http://app:8000` 로 주입(호스트 리맵과 무관).
