from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, require_water_quality_officer
from models.user import User
from schemas.wqi_weight import WqiWeightResponse, WqiWeightsUpdate
from services import wqi_weight_service

router = APIRouter(
    prefix="/wqi-weights",
    tags=["wqi-weights"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[WqiWeightResponse])
def list_weights(db: Session = Depends(get_db)):
    return wqi_weight_service.list_weights(db)


@router.post(
    "",
    response_model=list[WqiWeightResponse],
    status_code=status.HTTP_201_CREATED,
)
def create_weights(
    payload: WqiWeightsUpdate,
    actor: User = Depends(require_water_quality_officer),
    db: Session = Depends(get_db),
):
    return wqi_weight_service.create_weights(db, payload)


@router.put("", response_model=list[WqiWeightResponse])
def update_weights(
    payload: WqiWeightsUpdate,
    actor: User = Depends(require_water_quality_officer),
    db: Session = Depends(get_db),
):
    return wqi_weight_service.update_weights(db, payload)
