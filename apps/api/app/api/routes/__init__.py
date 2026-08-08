"""API route modules, assembled into a single versioned router."""

from fastapi import APIRouter

from app.api.routes import analytics, health, reviews, telemetry

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(analytics.router)
api_router.include_router(reviews.router)
api_router.include_router(telemetry.router)

__all__ = ["api_router"]
