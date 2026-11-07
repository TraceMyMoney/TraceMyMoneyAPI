from typing import Any

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page_number: int = Field(default=1, ge=1)
    per_page: int = Field(default=5, ge=1, le=10000)


class DateRange(BaseModel):
    """Date range filter."""

    start_date: str  # Format: "DD/MM/YYYY HH:MM"
    end_date: str | None = None


class AdvancedSearchParams(BaseModel):
    """Advanced search parameters for expenses."""

    bank_id: str | None = None
    search_by_tags: list[str] | None = None
    exclude_tags: list[str] | None = None
    search_by_bank_ids: list[str] | None = None
    search_by_keyword: str | None = None
    search_by_daterange: DateRange | None = None
    operator: str = Field(default="and", pattern="^(and|or)$")
    advanced_search: bool = False
    page_number: int = Field(default=1, ge=1)
    per_page: int = Field(default=5, ge=1, le=10000)


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: str


class ErrorResponse(BaseModel):
    """Generic error response."""

    error: str | list[Any]
