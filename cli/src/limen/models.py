from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class DispatchLogEntry(BaseModel):
    timestamp: datetime
    agent: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=256)
    status: str = Field(min_length=1, max_length=32)
    output: Optional[str] = Field(default=None, max_length=10000)


class Task(BaseModel):
    id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    title: str = Field(min_length=1, max_length=512)
    description: Optional[str] = Field(default=None, max_length=5000)
    repo: Optional[str] = Field(default=None, max_length=256)
    type: str = Field(default="code", min_length=1, max_length=32)
    target_agent: str = Field(min_length=1, max_length=32)
    priority: str = Field(default="medium", min_length=1, max_length=32)
    budget_cost: int = Field(default=1, ge=1, le=1000)
    status: str = Field(default="open", min_length=1, max_length=32)
    labels: list[str] = Field(default_factory=list, max_length=100)
    urls: list[str] = Field(default_factory=list, max_length=100)
    context: Optional[str] = Field(default=None, max_length=10000)
    claude_tier: Optional[str] = Field(default=None, max_length=32)
    depends_on: list[str] = Field(default_factory=list, max_length=100)
    created: date
    updated: Optional[datetime] = None
    dispatch_log: list[DispatchLogEntry] = Field(default_factory=list, max_length=1000)

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v: list[str]) -> list[str]:
        for label in v:
            if not (1 <= len(label) <= 256):
                raise ValueError("each label must be between 1 and 256 characters")
        return v

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: list[str]) -> list[str]:
        for url in v:
            if not (1 <= len(url) <= 2048):
                raise ValueError("each URL must be between 1 and 2048 characters")
        return v


class BudgetTrack(BaseModel):
    date: str = Field(default="", max_length=32)
    spent: int = Field(default=0, ge=0, le=1000000)
    per_agent: dict[str, int] = Field(default_factory=dict, max_length=100)
    per_agent_reset: dict[str, str] = Field(default_factory=dict, max_length=100)


class Budget(BaseModel):
    daily: int = Field(default=100, ge=1, le=100000)
    unit: str = Field(default="runs", min_length=1, max_length=64)
    per_agent: dict[str, int] = Field(default_factory=dict, max_length=100)
    track: BudgetTrack = Field(default_factory=lambda: BudgetTrack(date=""))


class Portal(BaseModel):
    name: str = Field(default="Universal Task Intake", min_length=1, max_length=256)
    description: str = Field(default="", max_length=2000)
    budget: Budget = Field(default_factory=Budget)


class LimenFile(BaseModel):
    version: str = Field(default="1.0", max_length=16)
    portal: Portal = Field(default_factory=Portal)
    tasks: list[Task] = Field(default_factory=list, max_length=100000)
