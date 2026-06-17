"""SEC EDGAR 현재 ticker→CIK 매핑 적재 — `company_tickers.json` fetch→저장→읽기.

진실 원천(추측·기억 금지): `docs/apis/sec-edgar/company-tickers.json`·`_index.json`.
엔드포인트·응답필드는 캡처된 명세 그대로만 사용한다(api-spec-reference 규칙).

명세 요지(2026-06-17 실측):
- `GET https://www.sec.gov/files/company_tickers.json` (정적 단일 파일·쿼리 없음).
- 응답 = 인덱스 문자열 키 맵 `{"0":{cik_str:int, ticker:str, title:str}, ...}`.
  ⚠️ 인덱스 키('0','1'…)는 행 번호라 **비안정** — `.values()` 로 순회(영구 키는 cik_str).
- 인증 **없음**(API 키 X). 단 SEC 공정접근 정책상 `User-Agent` 헤더에 신원(이름+이메일) 필수 —
  없으면 **403**(실측 확인). 토큰이 아니라 연락처라 비밀 아님.
- cik 포맷: 응답은 정수(320193) → data.sec.gov 사용처는 **10자리 zero-pad**("0000320193").
- 커버리지: SEC 신고 US operating companies 위주(ETF·외국주·비신고사 누락 가능 → 미해소 ticker 는
  호출부가 cik="" 폴백). '현재' 매핑만(폐지·과거 티커 미수록 — 생존편향 소스 아님).

저장: `{base_dir}/edgar/ticker_cik.json`. base_dir=parquet named volume 라 영속. 런타임
(backtest/api)은 이 저장본만 읽는다(라이브 SEC 호출은 이 진입점·ingest 만).

모듈 경계(python-conventions): `data` 는 `rules`/`backtest`/상위(api·webapp)를 import 하지 않는다.
이 파일은 외부 의존 httpx + stdlib 만(도메인 타입 불요 — ticker→cik 문자열 맵).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Final

import httpx

from . import configure_logging

logger = logging.getLogger(__name__)

_URL: Final = "https://www.sec.gov/files/company_tickers.json"
_IDENTITY_ENV: Final = "EDGAR_IDENTITY"
_DATA_DIR_ENV: Final = "STOCKPICK_DATA_DIR"
_DEFAULT_DATA_DIR: Final = "data/parquet"
_STORE_SUBPATH: Final = ("edgar", "ticker_cik.json")
_DEFAULT_TIMEOUT: Final = 30.0
_FORBIDDEN_STATUS: Final = 403


class EdgarError(RuntimeError):
    """EDGAR 어댑터 기반 예외."""


class EdgarIdentityError(EdgarError):
    """신원(User-Agent) 누락/거부 — EDGAR_IDENTITY 미설정 또는 SEC 403."""


class EdgarResponseError(EdgarError):
    """HTTP 4xx/5xx(403 제외) 또는 응답 파싱 실패."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def store_path(base_dir: Path) -> Path:
    """ticker→cik 저장 경로. base_dir 하위 `edgar/ticker_cik.json`(영속 볼륨 안)."""
    return base_dir.joinpath(*_STORE_SUBPATH)


def fetch_company_tickers(
    identity: str,
    *,
    client: httpx.Client | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, str]:
    """`company_tickers.json` → `{ticker(대문자): cik(10자리 zero-pad)}`. 라이브 SEC 호출.

    identity = User-Agent 신원(이름+이메일, SEC 필수). 빈값이면 EdgarIdentityError(SEC 403 회피).
    client 주입 가능(테스트 `httpx.MockTransport`). 403→EdgarIdentityError, 그 외 4xx/5xx·파싱실패→
    EdgarResponseError. 응답의 인덱스 키는 비안정 → `.values()` 순회. 형식 불량 엔트리는 추측 채움
    없이 누락(집계 WARNING).
    """
    if not identity.strip():
        msg = (
            f"환경변수 {_IDENTITY_ENV} 가 비어있습니다. SEC 는 User-Agent 신원(이름+이메일)을 "
            "요구합니다(없으면 403). .env 에 EDGAR_IDENTITY 설정."
        )
        raise EdgarIdentityError(msg)

    headers = {"User-Agent": identity, "Accept-Encoding": "gzip, deflate"}
    try:
        if client is not None:
            response = client.get(_URL, headers=headers)
        else:
            with httpx.Client(timeout=timeout) as c:
                response = c.get(_URL, headers=headers)
    except httpx.HTTPError as exc:
        msg = f"EDGAR company_tickers 요청 실패: {exc!r}"
        raise EdgarResponseError(msg) from exc

    if response.status_code == _FORBIDDEN_STATUS:
        msg = (
            "SEC 403 — User-Agent 신원이 거부됐습니다. EDGAR_IDENTITY(이름+이메일) 형식·값을 "
            "확인하세요(rate limit 초과도 차단 사유)."
        )
        raise EdgarIdentityError(msg)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        msg = f"EDGAR company_tickers HTTP {response.status_code}"
        raise EdgarResponseError(msg, status_code=response.status_code) from exc

    return _parse(response)


def _parse(response: httpx.Response) -> dict[str, str]:
    try:
        payload: object = response.json()
    except ValueError as exc:
        msg = "EDGAR company_tickers 응답 JSON 파싱 실패"
        raise EdgarResponseError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"EDGAR company_tickers 응답이 객체(dict)가 아님: {type(payload)}"
        raise EdgarResponseError(msg)

    mapping: dict[str, str] = {}
    dropped = 0
    for entry in payload.values():  # 인덱스 키 비안정 — 값만 순회
        if not isinstance(entry, dict):
            dropped += 1
            continue
        cik = entry.get("cik_str")
        ticker = entry.get("ticker")
        if not isinstance(cik, int) or not isinstance(ticker, str) or not ticker:
            dropped += 1
            continue
        mapping[ticker.upper()] = str(cik).zfill(10)
    if dropped:
        logger.warning("EDGAR company_tickers 형식 불량 %d행 누락(추측 채움 금지)", dropped)
    logger.info("EDGAR company_tickers 파싱: ticker→cik %d건", len(mapping))
    return mapping


def store_ticker_cik(mapping: dict[str, str], base_dir: Path) -> Path:
    """ticker→cik 맵을 `{base_dir}/edgar/ticker_cik.json` 에 저장(정렬·UTF-8). 경로 반환."""
    path = store_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    logger.info("EDGAR ticker→cik 저장: %s (%d건)", path, len(mapping))
    return path


def load_ticker_cik(base_dir: Path) -> dict[str, str]:
    """저장된 ticker→cik 맵을 읽는다. 파일 없으면 빈 맵(미적재 — cik="" 폴백·에러 아님)."""
    path = store_path(base_dir)
    if not path.is_file():
        logger.info("EDGAR ticker→cik 저장본 없음 — 빈 맵(미적재): %s", path)
        return {}
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        msg = f"EDGAR ticker_cik.json 형식 오류(dict 아님): {path}"
        raise EdgarError(msg)
    # 값 타입 좁히기(추측 캐스팅 금지 — 비문자열은 명시 실패).
    mapping: dict[str, str] = {}
    for ticker, cik in raw.items():
        if not isinstance(ticker, str) or not isinstance(cik, str):
            msg = f"EDGAR ticker_cik.json 항목 타입 오류: {ticker!r}->{cik!r}"
            raise EdgarError(msg)
        mapping[ticker] = cik
    return mapping


def main() -> int:
    """`python -m stockpick.data.edgar` — EDGAR_IDENTITY 로 fetch → base_dir 저장(진입점)."""
    configure_logging()
    identity = os.environ.get(_IDENTITY_ENV, "")
    if not identity.strip():
        print(f"[EDGAR] 환경변수 {_IDENTITY_ENV} 미설정 — SEC User-Agent 신원 필요(이름+이메일).")  # noqa: T201
        print("  → .env 에 EDGAR_IDENTITY 설정 후 컨테이너 재생성.")  # noqa: T201
        return 1
    base_dir = Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))
    mapping = fetch_company_tickers(identity)
    path = store_ticker_cik(mapping, base_dir)
    print(f"[EDGAR] ticker→cik {len(mapping)}건 저장: {path}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
