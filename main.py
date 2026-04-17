import os
from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from database import get_db, init_db, Load

load_dotenv()

API_KEY = os.getenv("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(title="HappyRobot Loads API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


def require_api_key(key: str = Security(api_key_header)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured on server")
    if key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return key


class StatusUpdate(BaseModel):
    status: str


def load_to_dict(load: Load) -> dict:
    return {
        "load_id": load.load_id,
        "origin": load.origin,
        "destination": load.destination,
        "pickup_datetime": load.pickup_datetime,
        "delivery_datetime": load.delivery_datetime,
        "equipment_type": load.equipment_type,
        "loadboard_rate": load.loadboard_rate,
        "notes": load.notes,
        "weight": load.weight,
        "commodity_type": load.commodity_type,
        "num_of_pieces": load.num_of_pieces,
        "miles": load.miles,
        "dimensions": load.dimensions,
        "status": load.status,
    }


@app.post("/admin/seed", dependencies=[Depends(require_api_key)])
def admin_seed(db: Session = Depends(get_db)):
    from seed import LOADS
    existing = db.query(Load).count()
    if existing > 0:
        return {"message": f"Database already has {existing} loads. Skipping seed."}
    for data in LOADS:
        db.add(Load(**data))
    db.commit()
    return {"message": f"Seeded {len(LOADS)} loads successfully."}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/loads", dependencies=[Depends(require_api_key)])
def get_loads(db: Session = Depends(get_db)):
    loads = db.query(Load).filter(Load.status == "available").all()
    return [load_to_dict(l) for l in loads]


@app.get("/loads/search", dependencies=[Depends(require_api_key)])
def search_loads(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    equipment_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Load)
    if origin:
        query = query.filter(Load.origin.ilike(f"%{origin}%"))
    if destination:
        query = query.filter(Load.destination.ilike(f"%{destination}%"))
    if equipment_type:
        query = query.filter(Load.equipment_type.ilike(f"%{equipment_type}%"))
    return [load_to_dict(l) for l in query.all()]


@app.get("/loads/{load_id}", dependencies=[Depends(require_api_key)])
def get_load(load_id: str, db: Session = Depends(get_db)):
    load = db.query(Load).filter(Load.load_id == load_id).first()
    if not load:
        raise HTTPException(status_code=404, detail=f"Load {load_id} not found")
    return load_to_dict(load)


@app.patch("/loads/{load_id}/status", dependencies=[Depends(require_api_key)])
def update_load_status(load_id: str, body: StatusUpdate, db: Session = Depends(get_db)):
    valid_statuses = {"available", "booked", "pending"}
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )
    load = db.query(Load).filter(Load.load_id == load_id).first()
    if not load:
        raise HTTPException(status_code=404, detail=f"Load {load_id} not found")
    load.status = body.status
    db.commit()
    db.refresh(load)
    return load_to_dict(load)
