from fastapi import APIRouter

from alpago.api.v1 import activity, approvals, auth, dashboard
from alpago.modules import (
    candidates, documents, employees, forms, hiring, interviews, offers,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(approvals.router)
api_router.include_router(hiring.router)
api_router.include_router(candidates.router)
api_router.include_router(interviews.router)
api_router.include_router(offers.router)
api_router.include_router(offers.public_router)
api_router.include_router(employees.router)
api_router.include_router(documents.router)
api_router.include_router(activity.router)
api_router.include_router(dashboard.router)
api_router.include_router(forms.router)
