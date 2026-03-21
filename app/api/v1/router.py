"""Top-level router for API v1."""

from fastapi import APIRouter

from app.api.v1.routes.ops import router as ops_router

api_router = APIRouter()
api_router.include_router(ops_router, tags=["ops"])
