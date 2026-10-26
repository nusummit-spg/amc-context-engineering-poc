# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
api/routes/scheme_aggregation_routes.py
========================================
REST API endpoints for scheme-level aggregation queries.
Provides dual-view responses (scheme-level + plan-level rankings) for mutual fund AUM analysis.
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional
import logging

from app.services.scheme_aggregation_service import get_aggregation_service
from app.models.scheme_aggregation import (
    DualViewAUMResponse,
    SchemeAggregationRequest
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/schemes/aggregation",
    tags=["Scheme Aggregation"],
    responses={404: {"description": "Not found"}},
)


@router.get(
    "/top-schemes",
    response_model=DualViewAUMResponse,
    summary="Get Top Schemes by Average AUM (Dual-View)",
    description="""
    Returns top mutual fund schemes ranked by Average AUM with dual-view response.
    
    **Scheme-Level View**: Aggregated metrics across all plan variants per scheme.
    **Plan-Level View**: Individual plan variants with specific AUM values.
    
    Use this endpoint for comprehensive scheme analysis and decision-making by AMC managers.
    """,
)
async def get_top_schemes(
    limit: int = Query(
        10,
        ge=1,
        le=100,
        description="Number of top schemes to return (1-100)"
    ),
    sort_by: str = Query(
        "max_aum",
        description="Sort by: 'max_aum' (default), 'avg_aum', 'total_aum', 'plan_count'"
    ),
    include_plan_details: bool = Query(
        True,
        description="Include detailed plan-level breakdown"
    ),
    include_inactive: bool = Query(
        False,
        description="Include closed/inactive schemes"
    ),
    min_plan_count: int = Query(
        1,
        ge=1,
        description="Minimum plan variants per scheme"
    ),
    amc_filter: Optional[str] = Query(
        None,
        description="Filter by specific AMC name (optional)"
    ),
    category_filter: Optional[str] = Query(
        None,
        description="Filter by scheme category, e.g., 'Equity Scheme - Large Cap Fund' (optional)"
    ),
):
    """
    Get top N mutual fund schemes with aggregated AUM metrics.
    
    Query Parameters:
    - limit: Number of results (1-100, default 10)
    - sort_by: Ranking criteria (max_aum, avg_aum, total_aum, plan_count)
    - include_plan_details: Include plan-level breakdown (default true)
    - include_inactive: Include closed schemes (default false)
    - min_plan_count: Minimum plan variants (default 1)
    - amc_filter: Filter by AMC (optional)
    - category_filter: Filter by scheme category (optional)
    
    Returns DualViewAUMResponse with:
    1. scheme_level_rankings: Aggregated scheme metrics
    2. plan_level_rankings: Individual plan variant details
    """
    try:
        service = get_aggregation_service()
        
        # Validate sort_by parameter
        valid_sorts = ['max_aum', 'avg_aum', 'total_aum', 'plan_count']
        if sort_by not in valid_sorts:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort_by. Must be one of: {', '.join(valid_sorts)}"
            )
        
        response = service.get_top_schemes(
            limit=limit,
            sort_by=sort_by,
            include_plan_details=include_plan_details,
            include_inactive=include_inactive,
            min_plan_count=min_plan_count,
            amc_filter=amc_filter,
            category_filter=category_filter,
        )
        
        logger.info(f"✓ Scheme aggregation query succeeded: {limit} schemes, sorted by {sort_by}")
        return response
        
    except ValueError as e:
        logger.error(f"✗ Data validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"✗ Unexpected error in scheme aggregation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/scheme/{scheme_name}",
    response_model=dict,
    summary="Get Single Scheme Aggregation Details",
    description="Fetch detailed aggregation metrics for a specific scheme across all plan types.",
)
async def get_scheme_details(scheme_name: str):
    """
    Get detailed aggregation metrics for a single scheme.
    
    Returns:
    - Scheme metadata
    - All plan variant details
    - Aggregated AUM metrics
    """
    try:
        service = get_aggregation_service()
        # This would need to be implemented in the service
        # For now, return a placeholder
        return {
            "message": "Endpoint placeholder - implement get_scheme_details in service",
            "scheme_name": scheme_name,
        }
    except Exception as e:
        logger.error(f"✗ Error fetching scheme details: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post(
    "/export-aggregations",
    response_model=dict,
    summary="Export Scheme Aggregations",
    description="Materialize and export scheme aggregations to CSV/Parquet for downstream use.",
)
async def export_aggregations(
    format: str = Query(
        "csv",
        description="Export format: 'csv' or 'parquet'"
    ),
):
    """
    Export materialized scheme aggregations.
    
    Useful for:
    - Caching aggregated metrics
    - Pre-computing rankings
    - Feeding into downstream dashboards/reports
    """
    try:
        service = get_aggregation_service()
        
        # Determine output path
        output_dir = "/tmp/scheme_aggregations"  # Should be configurable
        output_filename = f"scheme_aggregations.{format}"
        output_path = f"{output_dir}/{output_filename}"
        
        result_path = service.export_scheme_aggregations(output_path, format=format)
        
        logger.info(f"✓ Scheme aggregations exported to {result_path}")
        return {
            "status": "success",
            "message": f"Aggregations exported to {result_path}",
            "output_path": result_path,
            "format": format,
        }
    except Exception as e:
        logger.error(f"✗ Error exporting aggregations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/health",
    response_model=dict,
    summary="Health Check",
    description="Verify scheme aggregation service status.",
)
async def health_check():
    """Health check endpoint for the scheme aggregation service."""
    try:
        service = get_aggregation_service()
        data_source_info = service.get_data_source_info()
        
        return {
            "status": "healthy",
            "service": "scheme_aggregation",
            "rows_loaded": len(service.df) if service.df is not None else 0,
            "data_source": data_source_info,
            "message": "Scheme aggregation service is operational",
        }
    except Exception as e:
        logger.error(f"✗ Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "scheme_aggregation",
            "error": str(e),
        }


@router.get(
    "/chunks/health",
    response_model=dict,
    summary="Chunk Health Report",
    description="Get comprehensive health report for all data chunks.",
)
async def chunk_health_check():
    """Get chunk health report."""
    try:
        from app.services.chunk_manager import get_chunk_manager
        
        chunk_manager = get_chunk_manager()
        if not chunk_manager:
            return {
                "status": "unavailable",
                "message": "Chunk manager not available"
            }
        
        health_report = chunk_manager.get_health_report()
        
        return {
            "status": "success",
            "health_report": health_report,
        }
    except Exception as e:
        logger.error(f"✗ Chunk health check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


@router.get(
    "/chunks/statistics",
    response_model=dict,
    summary="Chunk Statistics",
    description="Get detailed statistics about data chunks.",
)
async def chunk_statistics():
    """Get chunk statistics."""
    try:
        from app.services.chunk_manager import get_chunk_manager
        
        chunk_manager = get_chunk_manager()
        if not chunk_manager:
            return {
                "status": "unavailable",
                "message": "Chunk manager not available"
            }
        
        stats = chunk_manager.get_chunk_statistics()
        
        return {
            "status": "success",
            "statistics": stats,
        }
    except Exception as e:
        logger.error(f"✗ Chunk statistics failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


@router.get(
    "/chunks/search/{scheme_name}",
    response_model=dict,
    summary="Search for Scheme in Chunks",
    description="Find which chunk contains a specific scheme.",
)
async def search_scheme_in_chunks(scheme_name: str):
    """Search for a scheme in chunks."""
    try:
        from app.services.chunk_manager import get_chunk_manager
        
        chunk_manager = get_chunk_manager()
        if not chunk_manager:
            return {
                "status": "unavailable",
                "message": "Chunk manager not available"
            }
        
        chunk_info = chunk_manager.get_chunk_by_scheme(scheme_name)
        
        if chunk_info:
            return {
                "status": "found",
                "scheme_name": scheme_name,
                "chunk_info": chunk_info,
            }
        else:
            return {
                "status": "not_found",
                "scheme_name": scheme_name,
                "message": f"Scheme '{scheme_name}' not found in chunks"
            }
    except Exception as e:
        logger.error(f"✗ Scheme search failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
