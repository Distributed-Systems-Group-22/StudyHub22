
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SummaryRequest(BaseModel):
    document_ids: list[str] = Field(
        min_length=1,
        max_length=20
    )
    instruction: str = Field(
        default="Generate a combined summary",
        min_length=1,
        max_length=2000
    )

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError("Document IDs cannot be empty")

        if len(values) != len(set(values)):
            raise ValueError("Duplicate document IDs are not allowed")

        return values


class SummaryJobResponse(BaseModel):
    job_id: UUID
    status: str
    cache_hit: bool


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: str
    attempts: int
    error_message: str | None = None
