from datetime import datetime
from typing import Optional

# Flask uses this format: "DD/MM/YYYY HH:MM"
DATE_TIME_FORMAT = "%d/%m/%Y %H:%M"


def parse_date_string(date_str: str) -> datetime:
    """Parse date string in Flask format to datetime object."""
    try:
        return datetime.strptime(date_str, DATE_TIME_FORMAT)
    except ValueError:
        # Try without time
        try:
            return datetime.strptime(date_str, "%d/%m/%Y")
        except ValueError:
            # Default to current time
            return datetime.utcnow()


def format_date(dt: datetime) -> str:
    """Format datetime to Flask format string."""
    return dt.strftime(DATE_TIME_FORMAT)
