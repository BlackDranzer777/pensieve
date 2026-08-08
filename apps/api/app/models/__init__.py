"""SQLAlchemy models.

Every model is imported here so that `Base.metadata` is complete after a single
`import app.models`. Alembic's autogenerate compares the live database against
that metadata, so a model this module forgets to import is a table Alembic will
cheerfully generate a migration to **drop**.
"""

from app.models.analytics import (
    Anomaly,
    CountryMetric,
    DailyBrandMetric,
    DailyTopicMetric,
    LanguageDistribution,
    SentimentTrend,
)
from app.models.base import Base
from app.models.core import Brand, Review, ReviewDateBounds, ReviewTopic
from app.models.telemetry import DataQualityResult, PipelineRun, PipelineStageRun

__all__ = [
    "Anomaly",
    "Base",
    "Brand",
    "CountryMetric",
    "DailyBrandMetric",
    "DailyTopicMetric",
    "DataQualityResult",
    "LanguageDistribution",
    "PipelineRun",
    "PipelineStageRun",
    "Review",
    "ReviewDateBounds",
    "ReviewTopic",
    "SentimentTrend",
]
