"""Redeeming an invitation, and claiming a recovery grant (architecture Part 10.2)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from charie.auth.guards import current_principal
from charie.auth.principal import Principal
from charie.invitations.service import accept_invitation
from charie.orgs.recovery import claim_recovery
from charie.orgs.service import ConflictError, ensure_user

router = APIRouter(prefix="/v1", tags=["invitations"])


class AcceptIn(BaseModel):
    token: str = Field(min_length=1)


class AcceptOut(BaseModel):
    org_id: uuid.UUID
    org_name: str
    role: str


@router.post("/invitations/accept", response_model=AcceptOut, summary="Redeem an invitation")
async def accept(
    body: AcceptIn, principal: Annotated[Principal, Depends(current_principal)]
) -> AcceptOut:
    user = await ensure_user(principal)
    try:
        accepted = await accept_invitation(user=user, token=body.token)
    except ConflictError as error:
        # One message for every failure — unknown.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return AcceptOut(org_id=accepted.org_id, org_name=accepted.org_name, role=accepted.role)


class ClaimRecoveryIn(BaseModel):
    token: str = Field(min_length=1)


class ClaimRecoveryOut(BaseModel):
    org_id: uuid.UUID
    org_name: str
    role: str
    was_member: bool = Field(
        description=(
            "True when you were already in this organization and have been "
            "raised to Admin; false when the claim also added you. Both are "
            "normal — the locked-out person is usually already a member."
        )
    )


@router.post(
    "/recovery-grants/claim",
    response_model=ClaimRecoveryOut,
    summary="Claim a recovery grant and become an Admin of its organization",
)
async def claim(
    body: ClaimRecoveryIn, principal: Annotated[Principal, Depends(current_principal)]
) -> ClaimRecoveryOut:
    """B-017. The way back into an organization whose Admins can no longer sign in."""
    user = await ensure_user(principal)
    try:
        claimed = await claim_recovery(user=user, token=body.token)
    except ConflictError as error:
        # One message for every failure — unknown, expired.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return ClaimRecoveryOut(
        org_id=claimed.org_id,
        org_name=claimed.org_name,
        role="admin",
        was_member=claimed.was_member,
    )
