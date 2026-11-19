from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Literal
from backend.cloud_config import require_admin
from backend import transport_selection as selection

router = APIRouter()


class Choice(BaseModel):
    transport: Literal["cloud", "warmlink_raw", "display_modbus", "standard_modbus"]


@router.get("/api/transport")
def current():
    return selection.initialize()


@router.post("/api/transport")
def select(payload: Choice, request: Request):
    require_admin(request)
    try:
        return selection.select(payload.transport)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
