"""Create initial train ETA tables."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("station_code", sa.String(length=16), nullable=False),
        sa.Column("station_name", sa.String(length=120), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
    )
    op.create_index("ix_stations_station_code", "stations", ["station_code"], unique=True)
    op.create_table(
        "trains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("train_number", sa.String(length=32), nullable=False),
        sa.Column("train_name", sa.String(length=120), nullable=False),
        sa.Column("source_station", sa.String(length=120), nullable=False),
        sa.Column("destination_station", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trains_train_number", "trains", ["train_number"], unique=True)
    op.create_index("ix_trains_status", "trains", ["status"])
    op.create_table(
        "train_routes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("train_id", sa.Integer(), sa.ForeignKey("trains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("scheduled_arrival", sa.DateTime(timezone=True)),
        sa.Column("scheduled_departure", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_train_routes_train_id", "train_routes", ["train_id"])
    op.create_index("ix_train_routes_station_id", "train_routes", ["station_id"])
    op.create_index(
        "ix_train_routes_train_sequence",
        "train_routes",
        ["train_id", "sequence_number"],
        unique=True,
    )
    op.create_table(
        "train_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("train_id", sa.Integer(), sa.ForeignKey("trains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("current_delay", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_train_positions_train_id", "train_positions", ["train_id"])
    op.create_index("ix_train_positions_recorded_at", "train_positions", ["recorded_at"])
    op.create_index("ix_train_positions_train_recorded", "train_positions", ["train_id", "recorded_at"])
    op.create_table(
        "eta_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("train_id", sa.Integer(), sa.ForeignKey("trains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("station_id", sa.Integer(), sa.ForeignKey("stations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("predicted_arrival", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_eta_predictions_train_id", "eta_predictions", ["train_id"])
    op.create_index("ix_eta_predictions_station_id", "eta_predictions", ["station_id"])
    op.create_index("ix_eta_predictions_predicted_at", "eta_predictions", ["predicted_at"])
    op.create_index(
        "ix_eta_predictions_train_station_predicted",
        "eta_predictions",
        ["train_id", "station_id", "predicted_at"],
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("train_id", sa.Integer(), sa.ForeignKey("trains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_alerts_train_id", "alerts", ["train_id"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_alerts_acknowledged", "alerts", ["acknowledged"])
    op.create_index("ix_alerts_train_created", "alerts", ["train_id", "created_at"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("eta_predictions")
    op.drop_table("train_positions")
    op.drop_table("train_routes")
    op.drop_table("trains")
    op.drop_table("stations")
