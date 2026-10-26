# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
api/routes/__init__.py
======================
Package initialization for API route modules.
Imports all route routers for registration in main.py.
"""

# Existing routes (keep these as they are)
from app.api.routes import (
    admin, auth, chat, compliance, docs, feedback, files, governance, graph,
    ingest, metrics, query, review_queue, sessions, status, taxonomy, 
    feedback_evaluation, audit
)

# New routes - Scheme Aggregation
try:
    from app.api.routes import scheme_aggregation_routes
except ImportError:
    scheme_aggregation_routes = None

__all__ = [
    'admin', 'auth', 'chat', 'compliance', 'docs', 'feedback', 'files',
    'governance', 'graph', 'ingest', 'metrics', 'query', 'review_queue',
    'sessions', 'status', 'taxonomy', 'feedback_evaluation', 'audit',
    'scheme_aggregation_routes'
]
