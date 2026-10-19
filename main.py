import json
import uuid
import os
import pathlib
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
import traceback

# In-memory SQLite on Render (reliable), file-based elsewhere
if os.getenv("RENDER"):
    SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
else:
    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./instigator.db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    budget = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)
    daily_cap = Column(Float, default=0.0)
    bid_price = Column(Float, default=1.0)
    geos = Column(JSON, default=list)
    creative_html = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class BidLog(Base):
    __tablename__ = "bid_logs"
    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer)
    request_id = Column(String)
    country = Column(String)
    bid_price = Column(Float)
    won = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Default Advertiser")
    credit_balance = Column(Float, default=1000.0)
    currency = Column(String, default="USD")

try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"DB create warning: {e}")

class CampaignCreate(BaseModel):
    name: str
    budget: float
    daily_cap: float
    bid_price: float
    geos: List[str]
    creative_html: str
    active: bool = True

class CampaignOut(BaseModel):
    id: int
    name: str
    budget: float
    spent: float
    daily_cap: float
    bid_price: float
    geos: List[str]
    creative_html: str
    active: bool
    class Config:
        from_attributes = True

app = FastAPI(title="Instigator DSP")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return PlainTextResponse(f"ERROR on {request.url.path}:\n\n{tb}", status_code=500)

BASE_DIR = pathlib.Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = None
try:
    if TEMPLATES_DIR.exists():
        templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
except Exception as e:
    print(f"Template warning: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def init_db():
    try:
        db = SessionLocal()
        if not db.query(Account).first():
            db.add(Account(name="Instigator Default", credit_balance=1000.0))
            db.commit()
        db.close()
    except Exception as e:
        print(f"init_db warning: {e}")

FALLBACK_HTML = """
<!DOCTYPE html>
<html>
<head><title>Instigator DSP</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100 p-8">
  <h1 class="text-4xl font-bold text-indigo-700">Instigator DSP</h1>
  <p class="mt-2">Dashboard is loading in fallback mode.</p>
  <p class="mt-4">OpenRTB endpoint: POST /openrtb/bid</p>
  <p>Health: <a href="/health" class="text-blue-600">/health</a></p>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    try:
        campaigns = db.query(Campaign).all()
        account = db.query(Account).first()
        if templates:
            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "campaigns": campaigns or [],
                "account": account,
                "title": "Instigator DSP"
            })
    except Exception as e:
        print(f"Dashboard error: {e}")
    return HTMLResponse(content=FALLBACK_HTML)

@app.post("/api/campaigns", response_model=CampaignOut)
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db)):
    db_campaign = Campaign(**campaign.dict())
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    return db_campaign

@app.get("/api/campaigns", response_model=List[CampaignOut])
def list_campaigns(db: Session = Depends(get_db)):
    return db.query(Campaign).all()

@app.put("/api/campaigns/{campaign_id}/toggle")
def toggle_campaign(campaign_id: int, db: Session = Depends(get_db)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.active = not campaign.active
    db.commit()
    return {"id": campaign.id, "active": campaign.active}

@app.post("/openrtb/bid")
async def openrtb_bid(request: Request, db: Session = Depends(get_db)):
    try:
        bid_request = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    request_id = bid_request.get("id", str(uuid.uuid4()))
    impressions = bid_request.get("imp", [])
    if not impressions:
        return JSONResponse(status_code=204, content={})

    device = bid_request.get("device", {})
    geo = device.get("geo", {})
    country = geo.get("country", "").upper()

    try:
        matching = db.query(Campaign).filter(
            Campaign.active == True,
            Campaign.spent < Campaign.budget
        ).all()
    except Exception:
        matching = []

    best_bid = None
    best_campaign = None
    for campaign in matching:
        if campaign.geos and country not in [g.upper() for g in (campaign.geos or [])]:
            continue
        if campaign.bid_price > 0 and (not best_bid or campaign.bid_price > best_bid["price"]):
            best_bid = {
                "price": campaign.bid_price,
                "adm": campaign.creative_html or "<div>Instigator Ad</div>"
            }
            best_campaign = campaign

    if not best_bid:
        return JSONResponse(status_code=204, content={})

    try:
        log = BidLog(
            campaign_id=best_campaign.id,
            request_id=request_id,
            country=country,
            bid_price=best_bid["price"]
        )
        db.add(log)
        db.commit()
    except Exception:
        pass

    return {
        "id": request_id,
        "seatbid": [{
            "bid": [{
                "id": str(uuid.uuid4()),
                "impid": impressions[0].get("id", "1"),
                "price": best_bid["price"],
                "adm": best_bid["adm"],
                "crid": f"instigator-{best_campaign.id}",
                "cid": str(best_campaign.id),
                "adid": str(best_campaign.id)
            }]
        }],
        "cur": "USD"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "service": "Instigator DSP", "db": "memory" if os.getenv("RENDER") else "file"}

@app.get("/billing")
def billing_info(db: Session = Depends(get_db)):
    try:
        account = db.query(Account).first()
        return {
            "credit_balance": account.credit_balance if account else 0,
            "currency": "USD"
        }
    except Exception:
        return {"credit_balance": 0, "currency": "USD"}
