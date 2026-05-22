from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        # Refuse to serve under a shared sentinel bucket — that path
        # re-creates the very cross-tenant leak we just closed.
        raise HTTPException(status_code=403, detail="Tenant not resolved for this user")

    revenue_data = await get_revenue_summary(property_id, tenant_id)

    # Pass the Decimal value through as a string. Casting to float here
    # collapses NUMERIC(10,3) into IEEE-754 and reintroduces the cent-level
    # drift the schema's sub-cent precision was chosen to avoid.
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
