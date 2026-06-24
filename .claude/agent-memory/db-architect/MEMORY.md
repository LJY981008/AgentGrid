# Memory Index

- [M1 저장 스키마 설계 결정](m1-storage-schema.md) — Parquet 파티셔닝·PG18 테이블·수정주가·PIT·생존편향 1급 설계 (2026-06-16)
- [마이그레이션 도구 미정 — ADR 선결](feedback-migration-tooling.md) — 직접 DDL 은 pre-bash-guard 차단, 마이그레이션 파일 전제. 첫 작업 시 alembic ADR 권고
- [S5-a PG 스키마 설계](s5a-pg-schema-design.md) — stock·ticker_history·daily_bar 첫 마이그레이션 + Parquet→PG 단방향 동기 + G1 순서 (2026-06-18)
- [DuckDB native peak 정적분석](duckdb-native-peak-analysis.md) — 백테스트 12.8GB native(window CTE 물질화·fetchall·threads 미설정) 가설 (2026-06-24)
- [EODHD $1M sentinel drop 정밀술어](eodhd-sentinel-1m-drop.md) — round(adjusted,2)=1000000.00 행단위(732,989행/793종목)·legit 무손실·종목drop 금지·3겹 필요 (2026-06-24)
- [EODHD adj_factor 임계 정밀](eodhd-adjfactor-threshold.md) — adj_factor 단독임계 위험(legit 거듭역분할 max 29k)·결합조건도 오제거·근원=sentinel÷close·close<=0.0005 페니floor 안전신호 (2026-06-24)
