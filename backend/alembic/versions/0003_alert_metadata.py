"""Add normalized metadata to operational alerts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_alert_metadata"
down_revision: Union[str, None] = "0002_realtime_source_quality"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("title", sa.String(length=160), nullable=False, server_default="Operational alert"))
    op.add_column("alerts", sa.Column("data_source", sa.String(length=16), nullable=False, server_default="DEMO"))
    op.add_column("alerts", sa.Column("data_quality", sa.String(length=16), nullable=False, server_default="SIMULATED"))
    op.add_column("alerts", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("alerts", "metadata_json")
    op.drop_column("alerts", "data_quality")
    op.drop_column("alerts", "data_source")
    op.drop_column("alerts", "title")