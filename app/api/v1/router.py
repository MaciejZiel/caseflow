"""Top-level router for API v1."""

from fastapi import APIRouter

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.cases import router as cases_router
from app.api.v1.routes.documents import case_router as case_documents_router
from app.api.v1.routes.documents import document_router as documents_router
from app.api.v1.routes.organizations import router as organizations_router

api_router = APIRouter()
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(cases_router, tags=["cases"])
api_router.include_router(case_documents_router, tags=["documents"])
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(organizations_router, tags=["organizations"])
