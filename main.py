import os
import traceback
from datetime import datetime

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool

print("=== Instigator DSP starting ===")

app = FastAPI(title="Instigator DSP")

# Database setup wrapped so it cannot kill startup
engine = None
SessionLocal = None
Base = declarative_base()
Campaign = None
Account = None

try:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    class Campaign(Base):
        __tablename__ = "campaigns"
        id = Column(Integer, primary_key=True, index=True)
        name = Column(String)
        budget = Column(Float, default=0.0)
        spent = Column(Float, default=0.0)
        daily_cap = Column(Float, default=0.0)
        bid_price = Column(Float, default=1.0)
        geos = Column(Text)
        creative_html = Column(Text)
        active = Column(Boolean, default=True)
        created_at = Column(DateTime, default=datetime.utcnow)

    class Account(Base):
        __tablename__ = "accounts"
        id = Column(Integer, primary_key=True)
        name = Column(String, default="Default")
        credit_balance = Column(Float, default=1000.0)
        currency = Column(String, default="USD")

    Base.metadata.create_all(bind=engine)
    print("Database ready")
except Exception as e:
    print("DB setup failed (continuing):", e)
    traceback.print_exc()

def get_db():
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def startup():
    print("Startup event")
    if SessionLocal is None:
        return
    try:
        db = SessionLocal()
        if Account and not db.query(Account).first():
            db.add(Account(name="Instigator", credit_balance=1000.0))
            db.commit()
        db.close()
        print("Startup OK")
    except Exception as e:
        print("Startup warning:", e)

@app.get("/health")
def health():
    return {"status": "ok", "db": engine is not None}

@app.get("/", response_class=HTMLResponse)
async def root():
    return """<!DOCTYPE html>
<html><head><title>Instigator DSP</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100 p-8">
<h1 class="text-4xl font-bold text-indigo-700">Instigator DSP</h1>
<p class="mt-4">Service is running.</p>
<p class="mt-2"><a href="/health" class="text-blue-600">/health</a></p>
<p class="mt-2"><a href="/test-create" class="text-blue-600">/test-create</a></p>
</body></html>"""

@app.get("/test-create")
def test_create(db: Session = Depends(get_db)):
    if db is None or Campaign is None:
        return {"error": "database not available"}
    try:
        obj = Campaign(name="Test", budget=50, bid_price=2.0, geos="GE")
        db.add(obj)
        db.commit()
        return {"ok": True, "id": obj.id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "tb": traceback.format_exc()})

@app.post("/api/campaigns")
async def create_campaign(request: Request, db: Session = Depends(get_db)):
    if db is None or Campaign is None:
        return JSONResponse(status_code=500, content={"error": "database not ready"})
    try:
        data = await request.json()
        geos_str = ",".join(data.get("geos") or [])
        obj = Campaign(
            name=str(data.get("name") or "Unnamed"),
            budget=float(data.get("budget") or 0),
            daily_cap=float(data.get("daily_cap") or 0),
            bid_price=float(data.get("bid_price") or 1),
            geos=geos_str,
            creative_html=str(data.get("creative_html") or ""),
            active=True,
        )
        db.add(obj)
        db.commit()
        return {"ok": True, "id": obj.id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "tb": traceback.format_exc()})

print("=== App defined, ready for uvicorn ===")
