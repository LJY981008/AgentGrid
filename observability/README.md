# 관측성 스택 (Prometheus + Grafana) — ADR-008

백테스트 perf·API·호스트 메모리 모니터링 + 최적화 라운드별 before/after 기록.

## 기동
```bash
docker compose up -d                 # 풀스택(app/web/postgres + prometheus/grafana/pushgateway)
```
- Grafana: http://localhost:3001 (익명 Admin·인증 없음·1인 로컬) · Prometheus: :9090 · Pushgateway: :9091
- 대시보드(레이어): **L1 신호등**(overview)·**L3 파이프라인**(백테스트 phase/perf)·**L4 무결성**·**인프라 호스트**(메모리). L2 외부의존·인프라 PG는 후속(exporter).

## 백테스트 프로파일 (peak/phase 측정) — ⚠️ app 정지 후 격리
풀 백테스트(~25분·peak ~12GB)는 app(`mem_limit:12g`)과 동시 가동 시 OOM → **격리 실행**:
```bash
docker compose stop app web
STOCKPICK_PROFILE_ROUND=before docker compose --profile profiling up profiler
# 실행 중: Prometheus 가 profiler:9100 scrape → L3/호스트 대시보드에 RSS·phase 라이브 곡선
# 종료 시: round=before 요약을 Pushgateway 에 push(영속)
docker compose up -d app web         # 끝나면 app 복구
```
출력 `[profile] ... rss_peak=X python_peak=Y` — **rss≫python 이면 peak 가 native(DuckDB C++)**, 비슷하면 Python.

## 최적화 before/after 스냅샷 (Grafana Local Snapshot)
1. 최적화 **전**: `STOCKPICK_PROFILE_ROUND=before` 로 profiler 실행 → 대시보드에 before 데이터.
2. Grafana 대시보드 → **Share → Snapshot → Local Snapshot** (grafana.db·grafana-data 볼륨 영속·데이터 동결).
3. 최적화 **후**: `STOCKPICK_PROFILE_ROUND=after` 실행 → 같은 대시보드에서 before/after 라벨 비교 + 새 Local Snapshot.
4. 스냅샷은 `http://localhost:3001/dashboard/snapshot/{key}` 로 영구 비교(라운드 누적).

## peak 메모리 할당 지점 (memray·런북·Prometheus 밖)
RSS Gauge·tracemalloc 으로 Python/native 귀속은 가리나, **할당 코드 줄**은 memray 로:
```bash
docker compose run --rm --no-deps app python -m memray run --temporal -o /tmp/bt.bin -m stockpick.backtest.profile
docker compose run --rm --no-deps app python -m memray flamegraph /tmp/bt.bin   # 할당지점 flamegraph
```
(tracemalloc 은 Python 힙만 — DuckDB C++ 버퍼면 memray 도 못 봄. 그 경우 답은 `connect_readonly` memory_limit.)
