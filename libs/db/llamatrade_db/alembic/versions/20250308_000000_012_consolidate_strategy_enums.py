"""Consolidate strategy enums to use proto definitions.

This migration:
1. Creates new PostgreSQL ENUM types for proto-defined enums
2. Removes strategy_type column from strategies table (no longer needed)
3. Removes strategy_type column from strategy_templates table
4. Converts category column in strategy_templates to template_category enum
5. Converts difficulty column in strategy_templates to template_difficulty enum
6. Adds asset_class column to strategy_templates
7. Drops the old strategy_type_enum PostgreSQL type
8. Creates notification_priority enum type

Proto enum value mappings:
- TemplateCategory: BUY_AND_HOLD=1, TACTICAL=2, FACTOR=3, INCOME=4, TREND=5,
                    MEAN_REVERSION=6, ALTERNATIVES=7
- AssetClass: EQUITY=1, FIXED_INCOME=2, MULTI_ASSET=3, CRYPTO=4, COMMODITY=5, OPTIONS=6
- IndicatorType: SMA=1, EMA=2, MACD=3, ADX=4, RSI=5, STOCHASTIC=6, CCI=7, WILLIAMS_R=8,
                 BOLLINGER_BANDS=9, ATR=10, KELTNER_CHANNEL=11, OBV=12, MFI=13, VWAP=14,
                 DONCHIAN_CHANNEL=15
- TemplateDifficulty: BEGINNER=1, INTERMEDIATE=2, ADVANCED=3
- NotificationPriority: LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4

Revision ID: 012_consolidate_strategy_enums
Revises: 011
Create Date: 2025-03-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_consolidate_strategy_enums"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Consolidate strategy enums to proto definitions."""

    # =========================================================================
    # STEP 1: CREATE NEW POSTGRES ENUM TYPES
    # =========================================================================

    # Template category (replaces strategy_type for templates)
    op.execute(
        "CREATE TYPE template_category AS ENUM "
        "('buy-and-hold', 'tactical', 'factor', 'income', 'trend', 'mean-reversion', 'alternatives')"
    )

    # Asset class for templates
    op.execute(
        "CREATE TYPE asset_class AS ENUM "
        "('equity', 'fixed-income', 'multi-asset', 'crypto', 'commodity', 'options')"
    )

    # Technical indicator types
    op.execute(
        "CREATE TYPE indicator_type AS ENUM "
        "('sma', 'ema', 'macd', 'adx', 'rsi', 'stochastic', 'cci', 'williams-r', "
        "'bollinger-bands', 'atr', 'keltner-channel', 'obv', 'mfi', 'vwap', 'donchian-channel')"
    )

    # Template difficulty
    op.execute("CREATE TYPE template_difficulty AS ENUM ('beginner', 'intermediate', 'advanced')")

    # Notification priority
    op.execute("CREATE TYPE notification_priority AS ENUM ('low', 'medium', 'high', 'critical')")

    # =========================================================================
    # STEP 2: DROP strategy_type FROM strategies TABLE
    # =========================================================================

    # Drop the index first
    op.drop_index("ix_strategies_tenant_type", table_name="strategies")

    # Drop the column
    op.drop_column("strategies", "strategy_type")

    # =========================================================================
    # STEP 3: UPDATE strategy_templates TABLE
    # =========================================================================

    # 3a. Convert category column to template_category enum
    # The existing category column already has kebab-case values that match our enum
    op.add_column("strategy_templates", sa.Column("category_enum", sa.String(30), nullable=True))
    op.execute("""
        UPDATE strategy_templates SET category_enum = CASE LOWER(category)
            WHEN 'buy-and-hold' THEN 'buy-and-hold'
            WHEN 'tactical' THEN 'tactical'
            WHEN 'factor' THEN 'factor'
            WHEN 'income' THEN 'income'
            WHEN 'trend' THEN 'trend'
            WHEN 'mean-reversion' THEN 'mean-reversion'
            WHEN 'alternatives' THEN 'alternatives'
            -- Map old strategy_type values if present in category
            WHEN 'trend_following' THEN 'trend'
            WHEN 'mean_reversion' THEN 'mean-reversion'
            WHEN 'momentum' THEN 'factor'
            WHEN 'breakout' THEN 'trend'
            WHEN 'custom' THEN 'alternatives'
            ELSE 'alternatives'
        END
    """)
    op.drop_column("strategy_templates", "category")
    op.execute("ALTER TABLE strategy_templates ADD COLUMN category template_category")
    op.execute("UPDATE strategy_templates SET category = category_enum::template_category")
    op.alter_column("strategy_templates", "category", nullable=False)
    op.drop_column("strategy_templates", "category_enum")

    # 3b. Drop strategy_type column from strategy_templates
    op.drop_column("strategy_templates", "strategy_type")

    # 3c. Convert difficulty column to template_difficulty enum
    op.add_column("strategy_templates", sa.Column("difficulty_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE strategy_templates SET difficulty_enum = CASE LOWER(difficulty)
            WHEN 'beginner' THEN 'beginner'
            WHEN 'intermediate' THEN 'intermediate'
            WHEN 'advanced' THEN 'advanced'
            ELSE 'beginner'
        END
    """)
    op.drop_column("strategy_templates", "difficulty")
    op.execute("ALTER TABLE strategy_templates ADD COLUMN difficulty template_difficulty")
    op.execute("UPDATE strategy_templates SET difficulty = difficulty_enum::template_difficulty")
    op.alter_column("strategy_templates", "difficulty", nullable=False)
    op.drop_column("strategy_templates", "difficulty_enum")

    # 3d. Add asset_class column with default value
    op.execute("ALTER TABLE strategy_templates ADD COLUMN asset_class asset_class")
    op.execute("UPDATE strategy_templates SET asset_class = 'equity'::asset_class")
    op.alter_column("strategy_templates", "asset_class", nullable=False)

    # =========================================================================
    # STEP 4: DROP OLD ENUM TYPE
    # =========================================================================

    op.execute("DROP TYPE IF EXISTS strategy_type_enum")


def downgrade() -> None:
    """Restore original strategy_type structure."""

    # =========================================================================
    # STEP 1: RECREATE strategy_type_enum
    # =========================================================================

    op.execute(
        "CREATE TYPE strategy_type_enum AS ENUM "
        "('trend_following', 'mean_reversion', 'momentum', 'breakout', 'custom')"
    )

    # =========================================================================
    # STEP 2: RESTORE strategy_templates TABLE
    # =========================================================================

    # 2a. Drop asset_class column
    op.drop_column("strategy_templates", "asset_class")

    # 2b. Convert difficulty back to string
    op.add_column("strategy_templates", sa.Column("difficulty_str", sa.String(20), nullable=True))
    op.execute("UPDATE strategy_templates SET difficulty_str = difficulty::text")
    op.alter_column("strategy_templates", "difficulty_str", nullable=False)
    op.drop_column("strategy_templates", "difficulty")
    op.alter_column("strategy_templates", "difficulty_str", new_column_name="difficulty")

    # 2c. Add back strategy_type column
    op.add_column(
        "strategy_templates",
        sa.Column(
            "strategy_type",
            sa.Enum(
                "trend_following",
                "mean_reversion",
                "momentum",
                "breakout",
                "custom",
                name="strategy_type_enum",
            ),
            nullable=True,
        ),
    )
    op.execute("UPDATE strategy_templates SET strategy_type = 'custom'::strategy_type_enum")
    op.alter_column("strategy_templates", "strategy_type", nullable=False)

    # 2d. Convert category back to string
    op.add_column("strategy_templates", sa.Column("category_str", sa.String(100), nullable=True))
    op.execute("UPDATE strategy_templates SET category_str = category::text")
    op.alter_column("strategy_templates", "category_str", nullable=False)
    op.drop_column("strategy_templates", "category")
    op.alter_column("strategy_templates", "category_str", new_column_name="category")

    # =========================================================================
    # STEP 3: RESTORE strategies TABLE
    # =========================================================================

    # Add back strategy_type column
    op.add_column(
        "strategies",
        sa.Column(
            "strategy_type",
            sa.Enum(
                "trend_following",
                "mean_reversion",
                "momentum",
                "breakout",
                "custom",
                name="strategy_type_enum",
                create_constraint=False,
            ),
            nullable=True,
        ),
    )
    op.execute("UPDATE strategies SET strategy_type = 'custom'::strategy_type_enum")
    op.alter_column("strategies", "strategy_type", nullable=False)

    # Recreate index
    op.create_index("ix_strategies_tenant_type", "strategies", ["tenant_id", "strategy_type"])

    # =========================================================================
    # STEP 4: DROP NEW ENUM TYPES
    # =========================================================================

    op.execute("DROP TYPE IF EXISTS notification_priority")
    op.execute("DROP TYPE IF EXISTS template_difficulty")
    op.execute("DROP TYPE IF EXISTS indicator_type")
    op.execute("DROP TYPE IF EXISTS asset_class")
    op.execute("DROP TYPE IF EXISTS template_category")
