from pydantic import AliasChoices, BaseModel, Field


class IngestSmsRequest(BaseModel):
    """Body of the SMS webhook. The field can be called text, message or body,
    so whatever name the phone automation uses works."""

    text: str = Field(..., min_length=1, max_length=2000, validation_alias=AliasChoices("text", "message", "body"))
    received_at: str | None = None  # ISO 8601; used when the SMS itself has no date

    model_config = {"populate_by_name": True}


class ConfirmPendingRequest(BaseModel):
    bank_id: str | None = None  # required unless the parser already matched an account
    description: str | None = Field(None, max_length=200)
    entry_tags: list[str] = Field(default_factory=list)
    amount: float | None = Field(None, gt=0)  # lets the user correct a mis-parsed amount
