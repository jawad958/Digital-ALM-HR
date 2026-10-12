from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from alpago.domain.approvals import ApprovalDecision


class CreateApprovalRequest(BaseModel):
    request_type: str = Field(min_length=1, max_length=60)
    subject_type: str = Field(min_length=1, max_length=60)
    subject_id: UUID
    context: dict = Field(default_factory=dict)


class ApprovalStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    step_index: int
    approver_role: str
    approver_user_id: UUID | None
    status: str
    comment: str | None
    activated_at: datetime | None
    decided_at: datetime | None
    sla_hours: int


class ApprovalRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    request_type: str
    subject_type: str
    subject_id: UUID
    submitter_user_id: UUID
    status: str
    current_step_index: int
    context: dict
    created_at: datetime
    decided_at: datetime | None
    steps: list[ApprovalStepOut]


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision
    comment: str | None = Field(default=None, max_length=2000)
