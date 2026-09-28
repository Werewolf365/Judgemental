"""Add theta_std and confidence to model_project_results (crowd-BT Laplace uncertainty).

theta_std: Laplace standard deviation from BFGS inverse-Hessian diagonal.
           NULL for legacy runs that predate this migration.
confidence: 'High' or 'Low' based on adjacent-rank P(A>B) < 0.90 threshold.
            Defaults to 'High' for legacy runs (they had no uncertainty info).

Revision ID: 0013_theta_std
Revises: 0012_bayes_overrides
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_theta_std"
down_revision = "0012_bayes_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # theta_std: nullable so old runs without Laplace info still load cleanly
    op.add_column("model_project_results",
                  sa.Column("theta_std", sa.Float(), nullable=True))
    # confidence: High/Low plain-language signal; default High for legacy rows
    op.add_column("model_project_results",
                  sa.Column("confidence", sa.Text(), nullable=False,
                            server_default="High"))


def downgrade() -> None:
    op.drop_column("model_project_results", "confidence")
    op.drop_column("model_project_results", "theta_std")
