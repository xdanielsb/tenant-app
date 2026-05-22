from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        # Refuse to serve under a shared sentinel bucket — that path
        # re-creates the very cross-tenant leak we just closed.
        raise HTTPException(status_code=403, detail="Tenant not resolved for this user")

    if (month is None) != (year is None):
        raise HTTPException(status_code=400, detail="month and year must be supplied together")

    revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)

    # Pass the Decimal value through as a string. Casting to float here
    # collapses NUMERIC(10,3) into IEEE-754 and reintroduces the cent-level
    # drift the schema's sub-cent precision was chosen to avoid.
    response: Dict[str, Any] = {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
    }
    if "period" in revenue_data:
        response["period"] = revenue_data["period"]
    return response
