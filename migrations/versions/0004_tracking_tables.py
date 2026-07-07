"""추적·보정 루프(M4) 4테이블 — portfolio_round / trade / cash_flow / corporate_action

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-02

사용자 생성 운용 데이터라 **PG 가 1차 진실**(시장데이터 Parquet 원칙의 명시 예외 — 스펙 §4).
설계 근거 = docs/superpowers/specs/2026-07-02-추적보정루프-design.md (6전문가 크리틱 반영):
- portfolio_round: 월 라운드 컨테이너. top20_snapshot(랭킹+rule_signature+validated+G-7 요약
  +anchor_close 동결·재현성)·carry_in(open 시점 이월 포지션 스냅샷)·retrospective(구조화 회고)·
  performance_snapshot(close 시 동결) 은 **불투명 JSONB**(형상은 코드 tracking/types 가 소유).
  open 라운드는 **전역 1개**(부분 UNIQUE — 규율 리추얼의 스키마 강제).
- trade: append-only 체결 원장. **stock_id FK**(티커 재사용 대비 안정 식별)+ticker(입력 당시
  사실 보존) 병기. 정정은 UPDATE/DELETE 아니라 **soft-void**(voided_at·void_reason 쌍 CHECK).
- cash_flow: 외부 입출금(signed·≠0). 입출금 없인 현금 원장·일별 TWR 산출 자체가 불능(C-2).
- corporate_action: SPLIT 이벤트 원장. adj_factor(분할+배당 혼합)를 수량 보정에 오용하지 않기
  위한 분리 소스(EODHD /splits). ratio = 신주/구주(2-for-1 → 2, 1:10 역분할 → 0.1).
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE portfolio_round (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            opened_on DATE NOT NULL,
            anchor_as_of DATE NOT NULL,
            top20_snapshot JSONB NOT NULL,
            rule_signature TEXT NOT NULL,
            validated BOOLEAN NOT NULL,
            g7_summary JSONB,
            carry_in JSONB NOT NULL DEFAULT '[]'::jsonb,
            discussion_memo TEXT,
            top5 JSONB,
            retrospective JSONB,
            performance_snapshot JSONB,
            closed_at TIMESTAMPTZ,
            CONSTRAINT portfolio_round_status_chk CHECK (status IN ('open', 'closed')),
            CONSTRAINT portfolio_round_label_uniq UNIQUE (label),
            -- closed 면 회고·성과 동결·closed_at 필수, open 이면 전부 NULL(반쪽 마감 금지)
            CONSTRAINT portfolio_round_closed_chk CHECK (
                (status = 'closed') = (closed_at IS NOT NULL)
                AND (status = 'closed') = (retrospective IS NOT NULL)
                AND (status = 'closed') = (performance_snapshot IS NOT NULL)
            )
        )
        """
    )
    # open 라운드 전역 1개 — 월 리추얼 강제(다음 라운드는 close 후에만).
    op.execute(
        "CREATE UNIQUE INDEX portfolio_round_open_uniq ON portfolio_round ((true)) "
        "WHERE status = 'open'"
    )

    op.execute(
        """
        CREATE TABLE trade (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            round_id BIGINT NOT NULL REFERENCES portfolio_round (id),
            stock_id BIGINT NOT NULL REFERENCES stock (id),
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity NUMERIC(20, 6) NOT NULL,
            price NUMERIC(20, 6) NOT NULL,
            fee NUMERIC(20, 6) NOT NULL DEFAULT 0,
            executed_on DATE NOT NULL,
            note TEXT,
            voided_at TIMESTAMPTZ,
            void_reason TEXT,
            CONSTRAINT trade_side_chk CHECK (side IN ('BUY', 'SELL')),
            CONSTRAINT trade_quantity_chk CHECK (quantity > 0),
            CONSTRAINT trade_price_chk CHECK (price > 0),
            CONSTRAINT trade_fee_chk CHECK (fee >= 0),
            -- soft-void 는 시각+사유 쌍으로만(감사 추적·물리 삭제/수정 금지)
            CONSTRAINT trade_void_pair_chk CHECK ((voided_at IS NULL) = (void_reason IS NULL))
        )
        """
    )
    op.execute("CREATE INDEX trade_round_idx ON trade (round_id)")
    op.execute("CREATE INDEX trade_executed_idx ON trade (executed_on, id)")

    op.execute(
        """
        CREATE TABLE cash_flow (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            round_id BIGINT NOT NULL REFERENCES portfolio_round (id),
            amount NUMERIC(20, 6) NOT NULL,
            flowed_on DATE NOT NULL,
            note TEXT,
            voided_at TIMESTAMPTZ,
            void_reason TEXT,
            CONSTRAINT cash_flow_amount_chk CHECK (amount <> 0),
            CONSTRAINT cash_flow_void_pair_chk CHECK ((voided_at IS NULL) = (void_reason IS NULL))
        )
        """
    )
    op.execute("CREATE INDEX cash_flow_round_idx ON cash_flow (round_id)")

    op.execute(
        """
        CREATE TABLE corporate_action (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            ticker TEXT NOT NULL,
            effective_on DATE NOT NULL,
            kind TEXT NOT NULL DEFAULT 'split',
            ratio NUMERIC(20, 12) NOT NULL,
            source TEXT NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT corporate_action_kind_chk CHECK (kind IN ('split')),
            CONSTRAINT corporate_action_ratio_chk CHECK (ratio > 0),
            CONSTRAINT corporate_action_uniq UNIQUE (ticker, effective_on)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS corporate_action")
    op.execute("DROP TABLE IF EXISTS cash_flow")
    op.execute("DROP TABLE IF EXISTS trade")
    op.execute("DROP INDEX IF EXISTS portfolio_round_open_uniq")
    op.execute("DROP TABLE IF EXISTS portfolio_round")
