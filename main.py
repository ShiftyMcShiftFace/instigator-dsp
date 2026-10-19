import os
import uuid
import traceback
from datetime import datetime
from typing import List, Any

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from pydantic import BaseModel

# Always use shared in-memory SQLite for reliability
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    budget = Column(Float, default=0.0)
    spent = Column(Float, default=0.0)
    daily_cap = Column(Float, default=0.0)
    bid_price = Column(Float, default=1.0)
    geos = Column(Text)  # store as comma-separated string to avoid JSON issues
    creative_html = Column(Text)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Default")
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
        Base.metadata.create_all(bind=engine)
        if not db.query(Account).first():
            db.add(Account(name="Instigator", credit_balance=1000.0))
            db.commit()
    except Exception as e:
        print("startup error:", e)
    finally:
        db.close()

def render_dashboard(campaigns, account):
    credit = f"${account.credit_balance:.2f}" if account else "$0.00"
    rows = ""
    if campaigns:
        for c in campaigns:
            geos = c.geos or "Global"
            status = "Active" if c.active else "Paused"
            rows += f"""
            <tr class="border-t">
              <td class="p-2">{c.name}</td>
              <td class="p-2">${c.budget:.2f}</td>
              <td class="p-2">${c.spent or 0:.2f}</td>
              <td class="p-2">${c.bid_price:.2f}</td>
              <td class="p-2">{geos}</td>
              <td class="p-2">{status}</td>
              <td class="p-2"><button onclick="toggleCampaign({c.id})" class="text-sm bg-gray-200 px-2 py-1 rounded">Toggle</button></td>
            </tr>"""
    else:
        rows = '<tr><td colspan="7" class="p-4 text-center text-gray-500">No campaigns yet.</td></tr>'

    return f"""<!DOCTYPE html>
<html>
<head><title>Instigator DSP</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100">
<div class="container mx-auto px-4 py-8">
  <h1 class="text-4xl font-bold text-indigo-700">Instigator DSP</h1>
  <div class="mt-2 bg-white p-4 rounded shadow inline-block">Credit: {credit}</div>
  <section class="mt-6 bg-white p-6 rounded shadow">
    <h2 class="text-2xl mb-4">Create Campaign</h2>
    <form id="campaignForm" class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <input id="name" placeholder="Name" class="border p-2 rounded" required>
      <input id="budget" type="number" step="0.01" placeholder="Budget" class="border p-2 rounded" required>
      <input id="daily_cap" type="number" step="0.01" placeholder="Daily Cap" class="border p-2 rounded">
      <input id="bid_price" type="number" step="0.01" placeholder="Bid CPM" class="border p-2 rounded" required>
      <input id="geos" placeholder="Geos: GE,RU,AE" class="border p-2 rounded md:col-span-2">
      <textarea id="creative_html" placeholder="Creative HTML" class="border p-2 rounded md:col-span-2" rows="2"></textarea>
      <button type="submit" class="bg-indigo-600 text-white px-4 py-2 rounded md:col-span-2">Create</button>
    </form>
  </section>
  <section class="mt-6 bg-white p-6 rounded shadow">
    <h2 class="text-2xl mb-4">Campaigns</h2>
    <table class="min-w-full"><thead><tr class="bg-gray-50"><th class="p-2 text-left">Name</th><th class="p-2 text-left">Budget</th><th class="p-2 text-left">Spent</th><th class="p-2 text-left">Bid</th><th class="p-2 text-left">Geos</th><th class="p-2 text-left">Status</th><th class="p-2 text-left">Action</th></tr></thead>
    <tbody>{rows}</tbody></table>
  </section>
  <section class="mt-6 bg-white p-4 rounded shadow">
    <p>OpenRTB: <code>POST /openrtb/bid</code></p>
    <p class="mt-2"><a href="/test-create" class="text-blue-600">Test create endpoint</a></p>
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
    creative_html: document.getElementById('creative_html').value || '<div>Ad</div>',
    active: true
  }};
  const res = await fetch('/api/campaigns', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(payload)
  }});
  const text = await res.text();
  if (res.ok) location.reload();
  else alert('Error: ' + text);
}});
async function toggleCampaign(id) {{
  await fetch('/api/campaigns/' + id + '/toggle', {{method: 'PUT'}});
  location.reload();
}}
</script>
</body></html>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard(db: Session = Depends(get_db)):
    try:
        campaigns = db.query(Campaign).all()
        account = db.query(Account).first()
    except Exception:
        campaigns = []
        account = None
    return HTMLResponse(render_dashboard(campaigns, account))

@app.post("/api/campaigns")
def create_campaign(campaign: CampaignCreate, db: Session = Depends(get_db)):
    try:
        geos_str = ",".join(campaign.geos) if campaign.geos else ""
        obj = Campaign(
            name=campaign.name,
            budget=float(campaign.budget),
            daily_cap=float(campaign.daily_cap),
            bid_price=float(campaign.bid_price),
            geos=geos_str,
            creative_html=campaign.creative_html or "",
            active=True,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return {"id": obj.id, "name": obj.name, "ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "tb": traceback.format_exc()})

@app.get("/test-create")
def test_create(db: Session = Depends(get_db)):
    try:
        obj = Campaign(name="Test", budget=100, bid_price=1.5, geos="GE", creative_html="<div>test</div>")
        db.add(obj)
        db.commit()
        return {"ok": True, "id": obj.id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "tb": traceback.format_exc()})

@app.put("/api/campaigns/{campaign_id}/toggle")
def toggle(campaign_id: int, db: Session = Depends(get_db)):
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        return JSONResponse(status_code=404, content={"error": "not found"})
    c.active = not c.active
    db.commit()
    return {"id": c.id, "active": c.active}

@app.post("/openrtb/bid")
async def openrtb_bid(request: Request, db: Session = Depends(get_db)):
    try:
        bid = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "bad json"})

    country = ((bid.get("device") or {}).get("geo") or {}).get("country", "").upper()
    try:
        campaigns = db.query(Campaign).filter(Campaign.active == True).all()
    except Exception:
        campaigns = []

    best = None
    best_c = None
    for c in campaigns:
        geos = [g.strip().upper() for g in (c.geos or "").split(",") if g.strip()]
        if geos and country not in geos:
            continue
        if not best or c.bid_price > best["price"]:
            best = {"price": c.bid_price, "adm": c.creative_html or "<div>Ad</div>"}
            best_c = c

    if not best:
        return JSONResponse(status_code=204, content={})

    return {{
        "id": bid.get("id", str(uuid.uuid4())),
        "seatbid": [{{"bid": [{{
            "id": str(uuid.uuid4()),
            "impid": (bid.get("imp") or [{}])[0].get("id", "1"),
            "price": best["price"],
            "adm": best["adm"],
            "crid": f"c{{best_c.id}}"
        }}]}}],
        "cur": "USD"
    }}

@app.get("/health")
def health():
    return {"status": "ok"}
