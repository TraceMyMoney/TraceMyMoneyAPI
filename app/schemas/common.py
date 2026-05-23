from typing import List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page_number: int = Field(default=1, ge=1)
    per_page: int = Field(default=5, ge=1, le=100)


class DateRange(BaseModel):
    """Date range filter."""

    start_date: str  # Format: "DD/MM/YYYY HH:MM"
    end_date: Optional[str] = None


class AdvancedSearchParams(BaseModel):
    """Advanced search parameters for expenses."""

    bank_id: Optional[str] = None
    search_by_tags: Optional[List[str]] = None
    search_by_bank_ids: Optional[List[str]] = None
    search_by_keyword: Optional[str] = None
    search_by_daterange: Optional[DateRange] = None
    operator: str = Field(default="and", pattern="^(and|or)$")
    advanced_search: bool = False
    page_number: int = Field(default=1, ge=1)
    per_page: int = Field(default=5, ge=1, le=100)


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: str


class ErrorResponse(BaseModel):
    """Generic error response."""

    error: str | List[Any]
