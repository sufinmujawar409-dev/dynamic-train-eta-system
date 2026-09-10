"""Store source and quality metadata for realtime records."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_realtime_source_quality"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("train_positions", sa.Column("data_source", sa.String(length=16), nullable=False, server_default="DEMO"))
    op.add_column("train_positions", sa.Column("data_quality", sa.String(length=16), nullable=False, server_default="SIMULATED"))
    op.add_column("eta_predictions", sa.Column("data_source", sa.String(length=16), nullable=False, server_default="DEMO"))
    op.add_column("eta_predictions", sa.Column("data_quality", sa.String(length=16), nullable=False, server_default="SIMULATED"))


def downgrade() -> None:
    op.drop_column("eta_predictions", "data_quality")
    op.drop_column("eta_predictions", "data_source")
    op.drop_column("train_positions", "data_quality")
    op.drop_column("train_positions", "data_source")