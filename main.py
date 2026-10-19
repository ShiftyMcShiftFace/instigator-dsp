import os
import uuid
import traceback
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, JSON, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from pydantic import BaseModel

# Shared in-memory SQLite (one database for all connections)
if os.getenv("RENDER"):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(
        os.getenv("DATABASE_URL", "sqlite:///./instigator.db"),
        connect_args={"check_same_thread": False},
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

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Default Advertiser")
    credit_balance = Column(Float, default=1000.0)
    currency = Column(String, default="USD")

Base.metadata.create_all(bind=engine)

class CampaignCreate(BaseModel):
    name: str
    budget: float
    daily_cap: float = 0.0
    bid_price: float
    geos: List[str] = []
    creative_html: str = ""
    active: bool = True

app = FastAPI(title="Instigator DSP")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def startup():
    db = SessionLocal()
    try:
        if not db.query(Account).first():
            db.add(Account(name="Instigator Default", credit_balance=1000.0))
            db.commit()
    finally:
        db.close()

def render_dashboard(campaigns, account):
    credit = f"${account.credit_balance:.2f} {account.currency}" if account else "$0.00"
    rows = ""
    if campaigns:
        for c in campaigns:
            geos = ", ".join(c.geos or []) if c.geos else "Global"
            status = "Active" if c.active else "Paused"
            rows += f"""
            <tr class="border-t">
              <td class="p-2">{c.name}</td>
              <td class="p-2">${c.budget:.2f}</td>
              <td class="p-2">${c.spent:.2f}</td>
              <td class="p-2">${c.bid_price:.2f}</td>
              <td class="p-2">{geos}</td>
              <td class="p-2">{status}</td>
              <td class="p-2"><button onclick="toggleCampaign({c.id})" class="text-sm bg-gray-200 px-2 py-1 rounded">Toggle</button></td>
            </tr>"""
    else:
        rows = '<tr><td colspan="7" class="p-4 text-center text-gray-500">No campaigns yet. Create one above.</td></tr>'

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Instigator DSP</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100">
  <div class="container mx-auto px-4 py-8">
    <header class="mb-8">
      <h1 class="text-4xl font-bold text-indigo-700">Instigator DSP</h1>
      <p class="text-gray-600">Demand Side Platform MVP</p>
      <div class="mt-2 bg-white p-4 rounded shadow inline-block">
        <span class="font-semibold">Credit Balance:</span> {credit}
      </div>
    </header>
    <section class="mb-8 bg-white p-6 rounded shadow">
      <h2 class="text-2xl font-semibold mb-4">Create Campaign</h2>
      <form id="campaignForm" class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <input type="text" id="name" placeholder="Campaign Name" class="border p-2 rounded" required>
        <input type="number" id="budget" placeholder="Total Budget ($)" step="0.01" class="border p-2 rounded" required>
        <input type="number" id="daily_cap" placeholder="Daily Cap ($)" step="0.01" class="border p-2 rounded">
        <input type="number" id="bid_price" placeholder="Bid Price (CPM $)" step="0.01" class="border p-2 rounded" required>
        <input type="text" id="geos" placeholder="Geos (comma-separated: GE,RU,AE,ZA)" class="border p-2 rounded md:col-span-2">
        <textarea id="creative_html" placeholder="Creative HTML" class="border p-2 rounded md:col-span-2" rows="3"></textarea>
        <button type="submit" class="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 md:col-span-2">Create Campaign</button>
      </form>
    </section>
    <section class="bg-white p-6 rounded shadow">
      <h2 class="text-2xl font-semibold mb-4">Campaigns</h2>
      <table class="min-w-full"><thead><tr class="bg-gray-50"><th class="text-left p-2">Name</th><th class="text-left p-2">Budget</th><th class="text-left p-2">Spent</th><th class="text-left p-2">Bid CPM</th><th class="text-left p-2">Geos</th><th class="text-left p-2">Status</th><th class="text-left p-2">Actions</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </section>
    <section class="mt-8 bg-white p-6 rounded shadow">
      <h2 class="text-2xl font-semibold mb-2">OpenRTB Endpoint</h2>
      <code class="block bg-gray-100 p-2 mt-2 rounded">POST /openrtb/bid</code>
    </section>
  </div>
  <script>
    document.getElementById('campaignForm').addEventListener('submit', async (e) => {{
      e.preventDefault();
      const geos = document.getElementById('geos').value.split(',').map(g => g.trim().toUpperCase()).filter(Boolean);
      const payload = {{
        name: document.getElementById('name').value,
        budget: parseFloat(document.getElementById('budget').value),
        daily_cap: parseFloat(document.getElementById('daily_cap').value) || 0,
        bid_price: parseFloat(document.getElementById('bid_price').value),
        geos: geos,
        creative_html: document.getElementById('creative_html').value || '<div>Instigator Ad</div>',
        active: true
      }};
      const res = await fetch('/api/campaigns', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify(payload)
      }});
      if (res.ok) {{
        location.reload();
      }} else {{
        const text = await res.text();
        alert('Error creating campaign: ' + text);
      }}
    }});
    async function toggleCampaign(id) {{
      await fetch('/api/campaigns/' + id + '/toggle', {{ method: 'PUT' }});
      location.reload();
    }}
  </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard(db: Session = Depends(get_db)):
    try:
        campaigns = db.query(Campaign).all()
        account = db.query(Account).first()
    except Exception as e:
        campaigns = []
        account = None
    return HTMLResponse(content=render_dashboard(campaigns, account))

@app.post("/api/campaigns")
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db)):
    try:
        db_campaign = Campaign(
            name=campaign.name,
            budget=float(campaign.budget),
            daily_cap=float(campaign.daily_cap),
            bid_price=float(campaign.bid_price),
            geos=list(campaign.geos or []),
            creative_html=campaign.creative_html or "",
            active=bool(campaign.active),
        )
        db.add(db_campaign)
        db.commit()
        db.refresh(db_campaign)
        return {{
            "id": db_campaign.id,
            "name": db_campaign.name,
            "budget": db_campaign.budget,
            "spent": db_campaign.spent or 0,
            "daily_cap": db_campaign.daily_cap or 0,
            "bid_price": db_campaign.bid_price,
            "geos": db_campaign.geos or [],
            "creative_html": db_campaign.creative_html or "",
            "active": db_campaign.active,
        }}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={{"error": str(e), "traceback": traceback.format_exc()}},
        )

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
    country = (geo.get("country") or "").upper()

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
        geos = campaign.geos or []
        if geos and country not in [g.upper() for g in geos]:
            continue
        if campaign.bid_price > 0 and (not best_bid or campaign.bid_price > best_bid["price"]):
            best_bid = {
                "price": campaign.bid_price,
                "adm": campaign.creative_html or "<div>Instigator Ad</div>",
            }
            best_campaign = campaign

    if not best_bid:
        return JSONResponse(status_code=204, content={})

    return {{
        "id": request_id,
        "seatbid": [{{
            "bid": [{{
                "id": str(uuid.uuid4()),
                "impid": impressions[0].get("id", "1"),
                "price": best_bid["price"],
                "adm": best_bid["adm"],
                "crid": f"instigator-{{best_campaign.id}}",
                "cid": str(best_campaign.id),
            }}]
        }}],
        "cur": "USD",
    }}

@app.get("/health")
def health():
    return {"status": "healthy", "service": "Instigator DSP"}
