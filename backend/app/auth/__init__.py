# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""Authentication module.

Layering (kept deliberately narrow so the JSON-backed store can be swapped
for a real database later without touching the API contract or the React
frontend):

    api/routes/auth.py   -> HTTP layer (request/response, status codes)
    auth/service.py       -> AuthService: authentication + session issuance
    auth/repository.py    -> UserRepository: where user records live today
                              (JSON file). Swap this for a SQL/ORM repository
                              later; AuthService and the routes never change.
    auth/security.py      -> password hashing + signed session tokens
"""
