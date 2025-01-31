from src_restful.resources.expense_entry_tags.views import ExpenseEntryTagResource
from src_restful.utils.common_utils import URLS

urls = [
    URLS(
        resource=ExpenseEntryTagResource,
        endpoint=["entry-tags-v1/"],
        name="Expense entry tag resource",
    )
]
