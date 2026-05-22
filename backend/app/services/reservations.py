from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Dict[str, Any]:
    """
    Calculates revenue for a specific calendar month in the property's
    local timezone. A Paris property's reservation at 2024-02-29 23:30 UTC
    is 2024-03-01 00:30 local and must count as March.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1-12, got {month}")

    start_local = datetime(year, month, 1)
    end_local = (
        datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    )

    from app.core.database_pool import DatabasePool

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        from sqlalchemy import text

        # AT TIME ZONE converts the TIMESTAMPTZ check_in_date into the
        # property's local naive timestamp, then we compare against naive
        # month bounds. This is the whole fix.
        query = text("""
            SELECT
                COALESCE(SUM(r.total_amount), 0) AS total_revenue,
                COUNT(*) AS reservation_count
            FROM reservations r
            JOIN properties p
              ON p.id = r.property_id AND p.tenant_id = r.tenant_id
            WHERE r.property_id = :property_id
              AND r.tenant_id  = :tenant_id
              AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_local
              AND (r.check_in_date AT TIME ZONE p.timezone) <  :end_local
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_local": start_local,
            "end_local": end_local,
        })
        row = result.fetchone()

        total = Decimal(str(row.total_revenue)) if row and row.total_revenue is not None else Decimal("0")
        count = row.reservation_count if row else 0

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total),
            "currency": "USD",
            "count": count,
            "period": f"{year:04d}-{month:02d}",
        }

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Import database pool
        from app.core.database_pool import DatabasePool
        
        # Initialize pool if needed
        db_pool = DatabasePool()
        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                query = text("""
                    SELECT 
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id
                })
                row = result.fetchone()
                
                if row:
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD", 
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        
        # Create property-specific mock data for testing when DB is unavailable
        # This ensures each property shows different figures
        mock_data = {
            'prop-001': {'total': '1000.00', 'count': 3},
            'prop-002': {'total': '4975.50', 'count': 4}, 
            'prop-003': {'total': '6100.50', 'count': 2},
            'prop-004': {'total': '1776.50', 'count': 4},
            'prop-005': {'total': '3256.00', 'count': 3}
        }
        
        mock_property_data = mock_data.get(property_id, {'total': '0.00', 'count': 0})
        
        return {
            "property_id": property_id,
            "tenant_id": tenant_id, 
            "total": mock_property_data['total'],
            "currency": "USD",
            "count": mock_property_data['count']
        }
