import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status, Query

from app.api.deps import CurrentUser, ExpenseServiceDep
from app.schemas.expense import ExpenseCreate, ExpenseListResponse
from app.schemas.expense_entry import ExpenseEntryCreate, ExpenseEntryUpdate, ExpenseEntryAddRequest
from app.schemas.common import AdvancedSearchParams

router = APIRouter()


@router.get("/")
async def get_expenses(
    current_user: CurrentUser, expense_service: ExpenseServiceDep, data: Optional[str] = Query(None),
    per_page: Optional[int] = Query(5), page_number: Optional[int] = Query(1), bank_id: Optional[str] = Query(None)
):
    if data:
        try:
            params_dict = json.loads(data)
            search_params = AdvancedSearchParams(**params_dict)
        except:
            search_params = AdvancedSearchParams(
                bank_id=bank_id, page_number=page_number, per_page=per_page
            )
    else:
        search_params = AdvancedSearchParams(bank_id=bank_id, page_number=page_number, per_page=per_page)

    expenses, total_count, non_topup_total, topup_total = await expense_service.get_expenses(
        current_user.id, search_params
    )

    return ExpenseListResponse(
        expenses=expenses, total_expenses=total_count, non_topup_total=non_topup_total, topup_total=topup_total,
    ).model_dump()


@router.get("/graph-data")
async def get_graph_data(
    current_user: CurrentUser, expense_service: ExpenseServiceDep, bank_id: Optional[str] = Query(None)
):
    """Get aggregated expense data by tags for graphs."""
    aggregated_data = await expense_service.get_aggregated_data(current_user.id, bank_id)
    return {"aggregated_data": aggregated_data}


@router.post("/create", status_code=201)
async def create_expense(
    expense_data: ExpenseCreate, current_user: CurrentUser, expense_service: ExpenseServiceDep
):
    """Create a new expense with entries."""
    try:
        expense = await expense_service.create_expense(current_user.id, expense_data)
        return {"success": "Docuement created successfully", "_id": expense.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e) if hasattr(e, "message") else "Error creating expense",
        )


@router.post("/create-bulk", status_code=201)
async def create_bulk_expenses(
    expenses_data: List[ExpenseCreate], current_user: CurrentUser, expense_service: ExpenseServiceDep
):
    """Create multiple expenses at once."""
    try:
        created_ids = []
        for expense_data in expenses_data:
            expense = await expense_service.create_expense(current_user.id, expense_data)
            created_ids.append(expense.id)

        return {"success": "Docuements inserted successfully", "ids": created_ids}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e) if hasattr(e, "message") else "Error creating expenses",
        )


@router.patch("/add-entry", status_code=201)
async def add_expense_entry(
    expense_service: ExpenseServiceDep,
    current_user: CurrentUser,
    id: str,
    entries: ExpenseEntryAddRequest = None,
):
    """Add new entries to an existing expense."""
    if not id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Please enter the expense ID to udpate"
        )

    result = await expense_service.add_expense_entries(current_user.id, id, entries.entries)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Expense not found for provided ID"
        )

    return {"success": "Added expense successfully"}


@router.patch("/update-entry", status_code=201)
async def update_expense_entry(
    entry_data: ExpenseEntryUpdate, current_user: CurrentUser, expense_service: ExpenseServiceDep
):
    """Update a specific expense entry."""
    if not entry_data.expense_id or not entry_data.entry_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide expense_id and entry_id"
        )

    if not entry_data.updated_description and not entry_data.selected_tags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide the tags or description"
        )

    result = await expense_service.update_expense_entry(current_user.id, entry_data)

    if not result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expense entry not found")

    return {"data": result}


@router.delete("/delete-entry", status_code=204)
async def delete_expense_entry(
    current_user: CurrentUser,
    expense_service: ExpenseServiceDep,
    id: str = Query(..., description="Expense ID"),
    ee_id: str = Query(..., description="Entry ID"),
):
    """Delete a specific expense entry."""
    if not id or not ee_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please enter the expense ID and entry ID to delete",
        )

    deleted = await expense_service.delete_expense_entry(current_user.id, id, ee_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Expense not found for provided ID"
        )

    return {"success": "Deleted expense entry successfully"}


@router.delete("/delete", status_code=204)
async def delete_expense(
    current_user: CurrentUser,
    expense_service: ExpenseServiceDep,
    id: str = Query(..., description="Expense ID"),
):
    """Delete an entire expense."""
    if not id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide the Expense ID"
        )

    deleted = await expense_service.delete_expense(current_user.id, id)

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return {"success": "Document deleted successfully"}
