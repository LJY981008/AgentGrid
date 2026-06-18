"""SEC EDGAR 어댑터 — (1) 현재 ticker→CIK 매핑(company_tickers) (2) XBRL 재무(companyfacts).

진실 원천(추측·기억 금지): `docs/apis/sec-edgar/company-tickers.json`·`companyfacts.json`·
`_index.json`. 엔드포인트·응답필드는 캡처된 명세 그대로만 사용(api-spec-reference 규칙).

(1) ticker→CIK (#2):
- `GET https://www.sec.gov/files/company_tickers.json` (정적 단일 파일·쿼리 없음).
- 응답 = 인덱스 문자열 키 맵 `{"0":{cik_str:int, ticker:str, title:str}, ...}`.
  ⚠️ 인덱스 키('0','1'…)는 행 번호라 **비안정** — `.values()` 로 순회(영구 키는 cik_str).
- cik 포맷: 응답은 정수(320193) → data.sec.gov 사용처는 **10자리 zero-pad**("0000320193").
- 커버리지: SEC 신고 US operating companies 위주(ETF·외국주·비신고사 누락 가능 → 미해소 ticker 는
  호출부가 cik="" 폴백). '현재' 매핑만(폐지·과거 티커 미수록 — 생존편향 소스 아님).
- 저장: `{base_dir}/edgar/ticker_cik.json`.

(2) XBRL 재무 companyfacts (#재무-1, ADR-005 — edgartools 미사용·직접 JSON 파싱):
- `GET https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (CIK 10자리 zero-pad).
- 응답 = `{cik, entityName, facts:{<taxonomy>:{<Concept>:{units:{<unit>:[fact...]}}}}}`.
  fact = `{end, val, filed, fy, fp, form, start?, frame?}`. 소수 concept(StockholdersEquity·
  NetIncomeLoss·EntityCommonStockSharesOutstanding)만 추출 → list[FinancialFact].
- ⚠️ PIT(룩어헤드 BLOCKING): disclosed_at=`filed`(공시일), period_end=`end`(회계기간말) 분리 —
  룩어헤드 가드는 `filed` 기준(rules/_financials 가 강제). NetIncomeLoss 는 연간(fp=FY)+분기 혼재.
- 저장: `{base_dir}/edgar/financials.json`(슬라이스 규모 — PG/Parquet 운영본은 결제·운영 후).

공통: 인증 **없음**(API 키 X). SEC 공정접근 정책상 `User-Agent` 헤더에 신원(이름+이메일) 필수 —
없으면 **403**(실측). 토큰 아니라 연락처라 비밀 아님(EDGAR_IDENTITY env). rate ~10 req/s. 런타임
(backtest/api)은 저장본만 읽는다(라이브 SEC 호출은 이 진입점·ingest 만).

모듈 경계(python-conventions): `data` 는 `rules`/`backtest`/상위(api·webapp)를 import 하지 않는다.
도메인 계약 `..types`(FinancialFact)는 import 가능(계약 원천).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final

import httpx

from ..types import FinancialFact
from . import configure_logging

logger = logging.getLogger(__name__)

_URL: Final = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL_TMPL: Final = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_IDENTITY_ENV: Final = "EDGAR_IDENTITY"
_DATA_DIR_ENV: Final = "STOCKPICK_DATA_DIR"
_DEFAULT_DATA_DIR: Final = "data/parquet"
_STORE_SUBPATH: Final = ("edgar", "ticker_cik.json")
_FINANCIALS_SUBPATH: Final = ("edgar", "financials.json")
_DEFAULT_TIMEOUT: Final = 30.0
_FORBIDDEN_STATUS: Final = 403

# ADR-005 슬라이스 concept — (taxonomy, concept bare tag).
# ROE=NetIncome/Equity · P/B 분모=Equity/shares.
_SLICE_CONCEPTS: Final[tuple[tuple[str, str], ...]] = (
    ("us-gaap", "StockholdersEquity"),
    ("us-gaap", "NetIncomeLoss"),
    ("dei", "EntityCommonStockSharesOutstanding"),
)


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


def financials_path(base_dir: Path) -> Path:
    """재무 fact 저장 경로. base_dir 하위 `edgar/financials.json`(영속 볼륨 안)."""
    return base_dir.joinpath(*_FINANCIALS_SUBPATH)


def fetch_companyfacts(
    cik: str,
    identity: str,
    *,
    concepts: tuple[tuple[str, str], ...] = _SLICE_CONCEPTS,
    client: httpx.Client | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[FinancialFact]:
    """companyfacts → 지정 concept 의 fact 만 list[FinancialFact]. 라이브 SEC 호출.

    cik = 10자리 zero-pad("0000320193"). identity = User-Agent 신원(빈값→IdentityError).
    concepts = (taxonomy, concept) 슬라이스(기본 _SLICE_CONCEPTS). 403→IdentityError, 그 외
    4xx/5xx·파싱실패→ResponseError. concept 결측은 정상(누락·집계 INFO). 형식불량 fact 는 추측
    채움 없이 누락(WARNING). PIT: disclosed_at=filed·period_end=end 분리(룩어헤드 가드는 호출부).
    """
    if not identity.strip():
        msg = (
            f"환경변수 {_IDENTITY_ENV} 가 비어있습니다. SEC 는 User-Agent 신원(이름+이메일)을 "
            "요구합니다(없으면 403). .env 에 EDGAR_IDENTITY 설정."
        )
        raise EdgarIdentityError(msg)
    if not cik.strip():
        msg = "fetch_companyfacts: cik 가 비어있습니다(ticker→cik 미해소 — 호출부에서 거름)."
        raise EdgarResponseError(msg)

    url = _FACTS_URL_TMPL.format(cik=cik)
    headers = {"User-Agent": identity, "Accept-Encoding": "gzip, deflate"}
    try:
        if client is not None:
            response = client.get(url, headers=headers)
        else:
            with httpx.Client(timeout=timeout) as c:
                response = c.get(url, headers=headers)
    except httpx.HTTPError as exc:
        msg = f"EDGAR companyfacts 요청 실패(cik={cik}): {exc!r}"
        raise EdgarResponseError(msg) from exc

    if response.status_code == _FORBIDDEN_STATUS:
        msg = "SEC 403 — User-Agent 신원 거부. EDGAR_IDENTITY 확인(rate limit 초과도 차단 사유)."
        raise EdgarIdentityError(msg)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        msg = f"EDGAR companyfacts HTTP {response.status_code}(cik={cik})"
        raise EdgarResponseError(msg, status_code=response.status_code) from exc

    return _parse_companyfacts(response, cik, concepts)


def _parse_companyfacts(
    response: httpx.Response,
    cik: str,
    concepts: tuple[tuple[str, str], ...],
) -> list[FinancialFact]:
    try:
        payload: object = response.json()
    except ValueError as exc:
        msg = f"EDGAR companyfacts 응답 JSON 파싱 실패(cik={cik})"
        raise EdgarResponseError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"EDGAR companyfacts 응답이 객체(dict)가 아님(cik={cik}): {type(payload)}"
        raise EdgarResponseError(msg)
    facts_root = payload.get("facts")
    if not isinstance(facts_root, dict):
        msg = f"EDGAR companyfacts 'facts' 누락/형식오류(cik={cik})"
        raise EdgarResponseError(msg)

    out: list[FinancialFact] = []
    dropped = 0
    missing: list[str] = []
    for taxonomy, concept in concepts:
        tax_node = facts_root.get(taxonomy)
        concept_node = tax_node.get(concept) if isinstance(tax_node, dict) else None
        units = concept_node.get("units") if isinstance(concept_node, dict) else None
        if not isinstance(units, dict):
            missing.append(f"{taxonomy}:{concept}")
            continue
        for unit_facts in units.values():  # 단위(USD/shares) 무관 — 전부 순회
            if not isinstance(unit_facts, list):
                continue
            for raw in unit_facts:
                fact = _build_fact(raw, cik=cik, concept=concept)
                if fact is None:
                    dropped += 1
                else:
                    out.append(fact)
    if missing:
        logger.info("EDGAR companyfacts concept 결측(cik=%s): %s", cik, ", ".join(missing))
    if dropped:
        logger.warning("EDGAR companyfacts 형식 불량 %d fact 누락(cik=%s·추측 금지)", dropped, cik)
    logger.info("EDGAR companyfacts 파싱(cik=%s): fact %d건", cik, len(out))
    return out


def _build_fact(raw: object, *, cik: str, concept: str) -> FinancialFact | None:
    """companyfacts fact dict → FinancialFact. 필수 필드 결측/형식불량이면 None(추측 금지)."""
    if not isinstance(raw, dict):
        return None
    end = raw.get("end")
    filed = raw.get("filed")
    val = raw.get("val")
    fy = raw.get("fy")
    fp = raw.get("fp")
    if not isinstance(end, str) or not isinstance(filed, str):
        return None
    if not isinstance(fp, str) or not isinstance(fy, int) or isinstance(fy, bool):
        return None
    if isinstance(val, bool) or not isinstance(val, int | float):
        return None
    try:
        period_end = date.fromisoformat(end)
        disclosed_at = date.fromisoformat(filed)
        value = Decimal(str(val))
    except (ValueError, InvalidOperation):
        return None
    return FinancialFact(
        cik=cik,
        concept=concept,
        fiscal_period=f"{fy}-{fp}",
        period_end=period_end,
        disclosed_at=disclosed_at,
        value=value,
    )


def store_financials(facts: list[FinancialFact], base_dir: Path) -> Path:
    """재무 fact 를 `{base_dir}/edgar/financials.json` 에 저장(Decimal→str·date→iso). 경로 반환."""
    path = financials_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = [
        {
            "cik": f.cik,
            "concept": f.concept,
            "fiscal_period": f.fiscal_period,
            "period_end": f.period_end.isoformat(),
            "disclosed_at": f.disclosed_at.isoformat(),
            "value": str(f.value),
        }
        for f in facts
    ]
    path.write_text(
        json.dumps(serialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    logger.info("EDGAR 재무 저장: %s (%d fact)", path, len(facts))
    return path


def _req_str(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        msg = f"EDGAR financials.json 필드 '{key}' 누락/비문자열: {value!r}"
        raise EdgarError(msg)
    return value


def load_financials(base_dir: Path) -> list[FinancialFact]:
    """저장된 재무 fact 읽기. 파일 없으면 빈 리스트(미적재·에러 아님). 형식오류→EdgarError."""
    path = financials_path(base_dir)
    if not path.is_file():
        logger.info("EDGAR 재무 저장본 없음 — 빈 리스트(미적재): %s", path)
        return []
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        msg = f"EDGAR financials.json 형식 오류(list 아님): {path}"
        raise EdgarError(msg)
    facts: list[FinancialFact] = []
    for item in raw:
        if not isinstance(item, dict):
            msg = f"EDGAR financials.json 항목이 dict 아님: {item!r}"
            raise EdgarError(msg)
        try:
            facts.append(
                FinancialFact(
                    cik=_req_str(item, "cik"),
                    concept=_req_str(item, "concept"),
                    fiscal_period=_req_str(item, "fiscal_period"),
                    period_end=date.fromisoformat(_req_str(item, "period_end")),
                    disclosed_at=date.fromisoformat(_req_str(item, "disclosed_at")),
                    value=Decimal(_req_str(item, "value")),
                )
            )
        except (ValueError, InvalidOperation) as exc:
            msg = f"EDGAR financials.json 항목 파싱 실패: {item!r}"
            raise EdgarError(msg) from exc
    return facts


def fetch_dataset_financials(
    base_dir: Path,
    identity: str,
    *,
    sleep_s: float = 0.12,
    client: httpx.Client | None = None,
) -> tuple[list[FinancialFact], list[str]]:
    """가격 데이터셋에 있는 ticker 의 cik 만 companyfacts fetch → (facts, 실패 cik). 10req/s 준수.

    데이터셋 ticker(`storage.list_dataset_tickers`) ∩ 저장된 ticker_cik 으로 대상 cik 산출
    (전체 수만 건 아님 — SEC 호출 최소·공정접근). cik 별 fetch 사이 sleep_s 대기(client 주입 시
    생략 — 테스트). 개별 cik 실패는 집계해 계속(전체 중단 안 함 — 실패 명확 보고).
    """
    from .storage import list_dataset_tickers  # 지연 import(pyarrow 로딩 — ticker 모드엔 불요)

    tickers = list_dataset_tickers(base_dir)
    ticker_cik = load_ticker_cik(base_dir)
    # ticker→cik 해소(미해소 ticker 건너뜀). cik 중복 제거(클래스주 GOOGL/GOOG = 동일 cik).
    target_ciks = sorted({ticker_cik[t] for t in tickers if ticker_cik.get(t)})
    logger.info(
        "재무 적재 대상: 데이터셋 ticker=%d, cik 해소=%d (저장 ticker_cik=%d)",
        len(tickers),
        len(target_ciks),
        len(ticker_cik),
    )
    all_facts: list[FinancialFact] = []
    failed: list[str] = []
    for i, cik in enumerate(target_ciks):
        if i > 0 and client is None:
            time.sleep(sleep_s)  # 공정접근(10req/s) — 라이브만. 테스트는 client 주입 시 생략.
        try:
            all_facts.extend(fetch_companyfacts(cik, identity, client=client))
        except EdgarError as exc:
            logger.warning("companyfacts fetch 실패(cik=%s): %r", cik, exc)
            failed.append(cik)
    return all_facts, failed


def main(argv: list[str] | None = None) -> int:
    """`python -m stockpick.data.edgar [financials]` — 기본=ticker→cik, 'financials'=companyfacts.

    공통: EDGAR_IDENTITY(User-Agent 신원) 필수. base_dir = STOCKPICK_DATA_DIR(기본 data/parquet).
    financials 모드는 ticker_cik 저장본·가격 데이터셋 선행 필요(둘의 교집합 cik 만 fetch).
    """
    configure_logging()
    args = sys.argv[1:] if argv is None else argv
    mode = args[0] if args else "tickers"
    identity = os.environ.get(_IDENTITY_ENV, "")
    if not identity.strip():
        print(f"[EDGAR] 환경변수 {_IDENTITY_ENV} 미설정 — SEC User-Agent 신원 필요(이름+이메일).")  # noqa: T201, E501
        print("  → .env 에 EDGAR_IDENTITY 설정 후 컨테이너 재생성.")  # noqa: T201
        return 1
    base_dir = Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))

    if mode == "financials":
        facts, failed = fetch_dataset_financials(base_dir, identity)
        path = store_financials(facts, base_dir)
        print(f"[EDGAR] 재무 fact {len(facts)}건 저장: {path}")  # noqa: T201
        if failed:
            print(f"[EDGAR] ⚠️ companyfacts 실패 cik {len(failed)}건: {', '.join(failed)}")  # noqa: T201
        return 0
    if mode != "tickers":
        print(f"[EDGAR] 알 수 없는 모드 '{mode}' — 'tickers'(기본) 또는 'financials'.")  # noqa: T201
        return 2

    mapping = fetch_company_tickers(identity)
    path = store_ticker_cik(mapping, base_dir)
    print(f"[EDGAR] ticker→cik {len(mapping)}건 저장: {path}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
