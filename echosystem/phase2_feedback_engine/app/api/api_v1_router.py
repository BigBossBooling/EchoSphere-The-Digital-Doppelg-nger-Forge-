# echosystem/phase2_feedback_engine/app/api/api_v1_router.py
from fastapi import APIRouter
# Adjusted import to be relative to the 'app' package,
# 'endpoints' is a sub-package of 'api'
from app.api.endpoints import feedback_endpoint
from app.api.endpoints import sandbox_orchestration_endpoint # Added import

api_router = APIRouter()

# Include the feedback ingestion endpoint router
# The prefix for this router will be combined with settings.API_V1_STR in main.py
# For example, if settings.API_V1_STR is "/api/v1/persona"
# and this router's prefix is "/feedback", the full path will be "/api/v1/persona/feedback"
api_router.include_router(
    feedback_endpoint.router,
    prefix="/feedback",
    tags=["Feedback Ingestion"]
)

# Include the persona sandbox orchestration endpoint router
# Example: if settings.API_V1_STR is "/api/v1/persona",
# full path will be "/api/v1/persona/sandboxes"
api_router.include_router(
    sandbox_orchestration_endpoint.router,
    prefix="/sandboxes", # Changed from /persona_sandboxes to just /sandboxes
    tags=["Persona Sandbox Orchestration"]
)
