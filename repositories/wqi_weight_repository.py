from sqlalchemy.orm import Session

from models.wqi_weight import WqiWeight


def list_weights(db: Session, lock: bool = False) -> list[WqiWeight]:
    query = db.query(WqiWeight).order_by(WqiWeight.parameter)
    if lock:
        query = query.with_for_update()
    return query.all()


def add_weights(db: Session, rows: list[WqiWeight]) -> list[WqiWeight]:
    db.add_all(rows)
    db.flush()
    return rows


def create_weight(db: Session, parameter: str, weight: float) -> WqiWeight:
    row = WqiWeight(parameter=parameter, weight=weight)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save(db: Session) -> None:
    db.commit()
