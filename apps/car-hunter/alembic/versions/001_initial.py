"""Initial schema — listings, scores, leasing, alert log.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("make", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("price_pln", sa.Float, nullable=False),
        sa.Column("mileage_km", sa.Integer, nullable=False),
        sa.Column("fuel_type", sa.String(50), nullable=False),
        sa.Column("transmission", sa.String(50), nullable=False),
        sa.Column("body_type", sa.String(50)),
        sa.Column("accident_history", sa.Boolean),
        sa.Column("seller_type", sa.String(50), nullable=False),
        sa.Column("location", sa.String(200)),
        sa.Column("raw_data", postgresql.JSONB),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_unique_constraint("uq_listings_source_external_id", "listings", ["source", "external_id"])
    op.create_index("ix_listings_make_model_year", "listings", ["make", "model", "year"])
    op.create_index("ix_listings_is_active", "listings", ["is_active"])

    op.create_table(
        "scored_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reliability_score", sa.Float, nullable=False),
        sa.Column("reliability_weight", sa.Float, nullable=False),
        sa.Column("maintenance_score", sa.Float, nullable=False),
        sa.Column("maintenance_weight", sa.Float, nullable=False),
        sa.Column("mileage_score", sa.Float, nullable=False),
        sa.Column("mileage_weight", sa.Float, nullable=False),
        sa.Column("service_history_score", sa.Float, nullable=False),
        sa.Column("service_history_weight", sa.Float, nullable=False),
        sa.Column("price_value_score", sa.Float, nullable=False),
        sa.Column("price_value_weight", sa.Float, nullable=False),
        sa.Column("resale_score", sa.Float, nullable=False),
        sa.Column("resale_weight", sa.Float, nullable=False),
        sa.Column("total_score", sa.Float, nullable=False),
        sa.Column("market_avg_price", sa.Float),
        sa.Column("price_deviation_pct", sa.Float),
        sa.Column("is_suspicious", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scored_total_score", "scored_listings", ["total_score"])

    op.create_table(
        "leasing_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("down_payment_pln", sa.Float, nullable=False),
        sa.Column("monthly_payment_pln", sa.Float, nullable=False),
        sa.Column("buyout_value_pln", sa.Float, nullable=False),
        sa.Column("term_months", sa.Integer, nullable=False),
        sa.Column("total_cost_pln", sa.Float, nullable=False),
        sa.Column("cost_per_year_pln", sa.Float, nullable=False),
        sa.Column("estimated_maintenance_yearly_pln", sa.Float, nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "alert_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("success", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("message_preview", sa.Text),
    )
    op.create_index("ix_alert_log_listing_channel", "alert_log", ["listing_id", "channel", "sent_at"])


def downgrade() -> None:
    op.drop_table("alert_log")
    op.drop_table("leasing_analyses")
    op.drop_table("scored_listings")
    op.drop_table("listings")
