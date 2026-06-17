"""API 설정·의존성 주입 — 테스트가 base_dir·source 를 오버라이드하는 지점.

Spring 비유: `@TestConfiguration` 으로 빈을 교체하듯, FastAPI `app.dependency_overrides` 로
프로덕션 코드를 안 건드리고 협력자(Parquet base_dir·EODHD source)만 바꿔치기한다. 덕분에 테스트는
라이브 호출 0(합성 Parquet 픽스처 + FakeSource 주입)으로 실제 DuckDB 스캔 경로를 탄다.

환경변수(없으면 기본값):
- STOCKPICK_DATA_DIR     Parquet base_dir       (기본 data/parquet)
- STOCKPICK_LEARNING_DIR docs/learning 디렉토리  (기본 docs/learning)
- STOCKPICK_CORS_ORIGINS CORS 허용 origin(쉼표)  (기본 http://localhost:5173 — Vite dev)
- (EODHD_API_KEY 는 어댑터가 호출 시점에 읽음 — api 층은 키를 보지 않는다)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from ..data.eodhd import EodhdSource
from ..data.source import DataSource

_DEFAULT_DATA_DIR = "data/parquet"
_DEFAULT_LEARNING_DIR = "docs/learning"
_DEFAULT_CORS_ORIGINS = "http://localhost:5173"


@lru_cache(maxsize=1)
def get_base_dir() -> Path:
    """Parquet base_dir. dataset·ranking 스캔 루트. 테스트는 dependency_overrides 로 tmp 주입."""
    return Path(os.environ.get("STOCKPICK_DATA_DIR", _DEFAULT_DATA_DIR))


@lru_cache(maxsize=1)
def get_learning_dir() -> Path:
    """docs/learning 디렉토리. 학습 트리·콘텐츠·StaticFiles 마운트 루트."""
    return Path(os.environ.get("STOCKPICK_LEARNING_DIR", _DEFAULT_LEARNING_DIR))


def get_cors_origins() -> list[str]:
    """CORS 허용 origin 목록(쉼표 구분 env). 개인 1인 로컬 — 기본 Vite dev 서버만."""
    raw = os.environ.get("STOCKPICK_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


def get_source() -> DataSource:
    """수집용 DataSource 팩토리. 기본 EodhdSource(라이브). 테스트는 FakeSource 로 오버라이드.

    ⚠️ EodhdSource() 생성자는 키를 읽지 않는다(어댑터가 fetch 시점에 EODHD_API_KEY 를 읽음).
    따라서 이 팩토리 자체는 키 없이 생성되며, 키 부재는 fetch 시점에 EodhdAuthError 로 표면화한다.
    """
    return EodhdSource()
