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
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final

import httpx

from ..types import FinancialFact
from . import configure_logging
from .checkpoint import Checkpoint

logger = logging.getLogger(__name__)

_URL: Final = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL_TMPL: Final = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_IDENTITY_ENV: Final = "EDGAR_IDENTITY"
_DATA_DIR_ENV: Final = "STOCKPICK_DATA_DIR"
_DEFAULT_DATA_DIR: Final = "data/parquet"
_STORE_SUBPATH: Final = ("edgar", "ticker_cik.json")
_FINANCIALS_SUBPATH: Final = ("edgar", "financials.json")
_FINANCIALS_CHECKPOINT_NAME: Final = "financials_checkpoint.jsonl"
_MIN_FISCAL_YEAR: Final = 2009  # XBRL 의무화 — 이전 재무는 sparse·불신(생존편향 시작점)
_DEFAULT_TIMEOUT: Final = 30.0
_FORBIDDEN_STATUS: Final = 403
_NOT_FOUND_STATUS: Final = 404  # companyfacts 없음(XBRL 미신고) — 영구·재시도 무의미

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
    start = raw.get("start")  # duration 개념(NetIncomeLoss)만 존재 — instant 는 없음
    if not isinstance(end, str) or not isinstance(filed, str):
        return None
    if not isinstance(fp, str) or not isinstance(fy, int) or isinstance(fy, bool):
        return None
    if isinstance(val, bool) or not isinstance(val, int | float):
        return None
    try:
        period_end = date.fromisoformat(end)
        disclosed_at = date.fromisoformat(filed)
        period_start = date.fromisoformat(start) if isinstance(start, str) else None
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
        period_start=period_start,
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
            "period_start": f.period_start.isoformat() if f.period_start is not None else None,
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
            raw_start = item.get("period_start")  # optional — instant 개념은 None/부재
            period_start = (
                date.fromisoformat(raw_start) if isinstance(raw_start, str) else None
            )
            facts.append(
                FinancialFact(
                    cik=_req_str(item, "cik"),
                    concept=_req_str(item, "concept"),
                    fiscal_period=_req_str(item, "fiscal_period"),
                    period_end=date.fromisoformat(_req_str(item, "period_end")),
                    disclosed_at=date.fromisoformat(_req_str(item, "disclosed_at")),
                    value=Decimal(_req_str(item, "value")),
                    period_start=period_start,
                )
            )
        except (ValueError, InvalidOperation) as exc:
            msg = f"EDGAR financials.json 항목 파싱 실패: {item!r}"
            raise EdgarError(msg) from exc
    return facts


def _fiscal_year(fact: FinancialFact) -> int:
    """fiscal_period "{fy}-{fp}" → fy(int). _build_fact 가 형식 보장 — 파싱 실패는 0(컷 제외)."""
    head = fact.fiscal_period.split("-", 1)[0]
    return int(head) if head.isdigit() else 0


def backfill_financials(
    base_dir: Path,
    identity: str,
    *,
    min_fiscal_year: int = _MIN_FISCAL_YEAR,
    sleep_s: float = 0.12,
    limit: int | None = None,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    """대상 cik companyfacts 를 cik 단위 증분 백필 → Parquet(financial_fact). Checkpoint resume.

    대상 cik = (가격 데이터셋 ticker ∩ ticker_cik) ∪ **폐지 복구 cik**(`delisted_cik.json`·A1·
    생존편향-안전 — 데이터셋에 가격 없어도 백필). cik 별 fetch → **fy≥min_fiscal_year**(XBRL 컷)
    필터 → `write_financial_facts`(cik 단위 덮어쓰기) → Checkpoint mark(done/empty). 개별 실패는
    failed 마킹·계속(전체 중단 안 함·재실행 시 failed 재시도). 10req/s 준수(client 주입 시 sleep
    생략 — 테스트). **limit**=미처리 cik 중 이번 호출 최대 처리수(단계 실행·resume 가 다음분 이어감·
    None=전체). 반환 = {target, done, empty, failed}.
    """
    from .cik_mapping import load_delisted_ciks
    from .storage import list_dataset_tickers, write_financial_facts  # pyarrow 지연 import

    tickers = list_dataset_tickers(base_dir)
    ticker_cik = load_ticker_cik(base_dir)
    # cik 중복 제거(클래스주 GOOGL/GOOG = 동일 cik). 폐지 복구 cik union(생존편향-안전).
    active_ciks = {ticker_cik[t] for t in tickers if ticker_cik.get(t)}
    delisted_ciks = {cik for cik, _delisted in load_delisted_ciks(base_dir).values()}
    target_ciks = sorted(active_ciks | delisted_ciks)

    checkpoint = Checkpoint.load(base_dir / _FINANCIALS_CHECKPOINT_NAME)
    stamp = datetime.now(UTC)
    logger.info(
        "재무 백필 시작: 대상 cik=%d(데이터셋∩cik=%d, 폐지=%d, 저장 ticker_cik=%d)",
        len(target_ciks),
        len(active_ciks),
        len(delisted_ciks),
        len(ticker_cik),
    )
    fetched = 0
    for cik in target_ciks:
        if checkpoint.should_skip(cik):
            continue
        if limit is not None and fetched >= limit:
            break  # 단계 실행 — 이번 호출 한도 도달(나머지는 다음 호출이 resume)
        if fetched > 0 and client is None:
            time.sleep(sleep_s)  # 공정접근(10req/s) — 라이브만. 테스트는 client 주입 시 생략.
        fetched += 1
        try:
            facts = fetch_companyfacts(cik, identity, client=client)
        except EdgarResponseError as exc:
            if exc.status_code == _NOT_FOUND_STATUS:
                checkpoint.mark(cik, "empty")  # companyfacts 없음(XBRL 미신고·영구) — 재시도 무의미
            else:
                logger.warning("companyfacts fetch 실패(cik=%s): %r", cik, exc)
                checkpoint.mark(cik, "failed")  # 일시 오류(5xx 등) — 재실행 재시도
            continue
        except EdgarError as exc:  # IdentityError 등 — 재시도 대상
            logger.warning("companyfacts fetch 실패(cik=%s): %r", cik, exc)
            checkpoint.mark(cik, "failed")
            continue
        recent = [f for f in facts if _fiscal_year(f) >= min_fiscal_year]
        if recent:
            write_financial_facts(recent, base_dir, source="sec-edgar", ingested_at=stamp)
            checkpoint.mark(cik, "done")  # ⚠️ write 완료 후에만(부분적재 재개 회복)
        else:
            checkpoint.mark(cik, "empty")  # fetch 성공·적재할 fact 0(fy 컷·concept 결측)
    counts = checkpoint.counts()
    logger.info("재무 백필 완료: 대상=%d, %s", len(target_ciks), counts)
    return {"target": len(target_ciks), **counts}


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
        limit: int | None = None
        if "--limit" in args:
            idx = args.index("--limit")
            if idx + 1 < len(args):
                limit = int(args[idx + 1])
        counts = backfill_financials(base_dir, identity, limit=limit)
        print(  # noqa: T201
            f"[EDGAR] 재무 백필: 대상 {counts['target']}cik · "
            f"done={counts['done']} empty={counts['empty']} failed={counts['failed']} "
            f"→ financial_fact/(Parquet)"
        )
        if counts["failed"]:
            print(f"[EDGAR] ⚠️ 실패 {counts['failed']}cik — 재실행 시 재시도(Checkpoint).")  # noqa: T201
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
