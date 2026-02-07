from typing import Optional
from fastapi import APIRouter, HTTPException, status, Query
from app.api.deps import CurrentUser, BankServiceDep
from app.schemas.bank import BankCreate, BankResponse
from app.schemas.common import SuccessResponse

router = APIRouter()


@router.get("/", response_model=dict)
async def get_banks(
    current_user: CurrentUser,
    bank_service: BankServiceDep,
    id: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
):
    """Get all banks for the current user with optional filters."""
    banks = await bank_service.get_banks(current_user.id, bank_id=id, name=name)

    return {
        "banks": [
            {
                "id": bank.id,
                "name": bank.name,
                "initial_balance": bank.initial_balance,
                "current_balance": bank.current_balance,
                "total_disbursed_till_now": bank.total_disbursed_till_now,
                "created_at": bank.created_at,
            }
            for bank in banks
        ]
    }


@router.post("/create", status_code=200)
async def create_bank(bank_data: BankCreate, current_user: CurrentUser, bank_service: BankServiceDep):
    """Create a new bank account."""
    try:
        bank = await bank_service.create_bank(current_user.id, bank_data)
        return {"success": "Bank object saved successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Error while saving the bank object"
        )


@router.delete("/delete", status_code=204)
async def delete_bank(
    current_user: CurrentUser,
    bank_service: BankServiceDep,
    bank_id: str = Query(..., description="Bank ID to delete"),
):
    """Delete a bank and all associated expenses."""
    deleted = await bank_service.delete_bank(current_user.id, bank_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Bank not found with provided ID"
        )

    return SuccessResponse(success="Bank deleted successfully")
