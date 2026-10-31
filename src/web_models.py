"""Strict public HTTP contracts; domain state and dispatch policy stay in services."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Message must not be blank")
    return value


def _numeric_input(value: object) -> object:
    # Existing UI/API clients may send a numeric input as a string. Booleans
    # remain invalid, and Pydantic enforces finiteness and bounds afterwards.
    return float(value) if isinstance(value, str) else value


Message = Annotated[str, Field(min_length=1, max_length=32000), AfterValidator(_nonblank)]
IntervalMinutes = Annotated[
    float, Field(ge=0.1, le=43200, allow_inf_nan=False), BeforeValidator(_numeric_input)
]
DelayMinutes = Annotated[
    float, Field(ge=0, le=43200, allow_inf_nan=False), BeforeValidator(_numeric_input)
]
DailyTime = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
]
BranchId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{16,200}$")]
RequestId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
ImageRef = Annotated[str, Field(pattern=r"^[0-9a-f]{64}/[A-Za-z0-9._-]{1,100}$")]


class RequestModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)


class ErrorResponse(BaseModel):
    ok: Literal[False] = False
    error: str


class EmptyRequest(RequestModel):
    pass


class ReplyRequest(RequestModel):
    reply_id: BranchId
    conversation_id: BranchId
    parent_id: BranchId
    text: Message


class FollowupRequest(RequestModel):
    reply_id: BranchId
    text: Message


class FreshChatRequest(RequestModel):
    request_id: RequestId
    prompt: Message
    images: Annotated[list[ImageRef], Field(max_length=4)]


class ImageUpload(RequestModel):
    name: str
    data: str


class PinRequest(RequestModel):
    send_id: str
    pinned: bool


class PinImport(RequestModel):
    send_ids: list[str]


class ReadRequest(RequestModel):
    send_id: str
    revision: str


class ReadImport(RequestModel):
    reads: dict[str, str]


class ResultsQuery(BaseModel):
    # Query strings require numeric decoding; JSON bodies remain strictly typed.
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    limit: Annotated[int, Field(ge=1, le=50)] = 20
    offset: Annotated[int, Field(ge=0, le=100_000)] = 0
    q: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    status: Literal[
        "", "queued", "accepted", "generating", "completed", "interrupted", "unavailable",
        "needs_attention",
    ] = ""


class AddJob(RequestModel):
    action: Literal["add"]
    name: NonBlank
    prompt: NonBlank
    schedule: Literal["once", "interval", "daily"] = "interval"
    images: Annotated[list[ImageRef], Field(max_length=4)] = Field(default_factory=list)
    mutex_group: str = ""
    pin_chat: bool = False
    daily_at: DailyTime | Literal[""] | None = None
    interval_minutes: IntervalMinutes | None = None
    delay_minutes: DelayMinutes = 0
    exact_interval: bool = False

    @model_validator(mode="after")
    def cadence(self) -> Self:
        if self.schedule != "once" and not self.daily_at and self.interval_minutes is None:
            raise ValueError("Interval minutes are required for an interval job")
        if self.schedule == "daily" and not self.daily_at:
            raise ValueError("Daily time is required for a daily job")
        return self


class RunOnce(RequestModel):
    action: Literal["run_once"]
    prompt: NonBlank
    images: Annotated[list[ImageRef], Field(max_length=4)] = Field(default_factory=list)
    delay_minutes: DelayMinutes = 0
    pin_chat: bool = False
    request_id: RequestId | None = None


class NamedJobAction(RequestModel):
    action: Literal["remove", "pause", "resume", "fire_now"]
    name: NonBlank
    request_id: RequestId | None = None


class ManyJobAction(RequestModel):
    action: Literal["pause_many", "resume_many"]
    names: Annotated[list[NonBlank], Field(min_length=1)]


class AllJobAction(RequestModel):
    action: Literal["pause_all", "resume_all", "clear"]


JobAction = Annotated[
    AddJob | RunOnce | NamedJobAction | ManyJobAction | AllJobAction, Field(discriminator="action")
]

JOB_ACTION = TypeAdapter(JobAction)
