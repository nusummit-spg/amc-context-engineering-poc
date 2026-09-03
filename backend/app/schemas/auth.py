# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ===========================================================================

"""Auth API request/response contract — shared with the React frontend."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)
    remember_me: bool = False


class UserPublic(BaseModel):
    """Everything the frontend is allowed to see about a user. No password/hash fields."""
    username: str
    display_name: str
    role: str
    department: str = ""
    email: str = ""
    avatar_initials: str = ""
    status: str = "Active"


class LoginResponse(BaseModel):
    token: str
    expires_at: int
    user: UserPublic


class MeResponse(BaseModel):
    user: UserPublic
