import os
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import String, Float, Boolean, DateTime, JSON, select, func, desc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("CashPulse")

DB_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./fintech.db")
engine = create_async_engine(DB_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def _uuid(): return str(uuid.uuid4())
def _utcnow(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    baseline_income: Mapped[float] = mapped_column(Float, default=0.0)

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    account_type: Mapped[str] = mapped_column(String(20), default="checking")
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")

class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    amount: Mapped[float] = mapped_column(Float)
    transaction_type: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(64), default="uncategorized")
    merchant_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False)

class PendingAction(Base):
    __tablename__ = "pending_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(String(1024))
    suggested_action_type: Mapped[str] = mapped_column(String(50))
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    ai_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

class TransactionCreate(BaseModel):
    account_id: str
    amount: float = Field(..., gt=0)
    transaction_type: str
    category: str = "general"
    merchant_name: Optional[str] = None
    is_recurring: bool = False

class ScenarioRequest(BaseModel):
    user_id: str
    scenario_description: str
    horizon_days: int = 90

class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")

async def seed_if_empty():
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(User).limit(1))
        if not existing:
            user = User(id="user-demo-001", name="Rahul Sharma", email="rahul@example.com", baseline_income=90000.0)
            acc = Account(id="acc-demo-001", user_id="user-demo-001", balance=125000.0, currency="INR")
            db.add_all([user, acc])

            now = _utcnow()
            txns = [
                (90000.0, "credit", "salary", "TechCorp Salary", 25, True, False),
                (28000.0, "debit", "housing", "Apartment Rent", 24, True, False),
                (1499.0, "debit", "utilities", "JioAirFiber", 20, True, False),
                (649.0, "debit", "entertainment", "Netflix", 18, True, False),
                (1200.0, "debit", "food", "Swiggy", 12, False, False),
                (4200.0, "debit", "groceries", "Blinkit", 8, False, False),
                (21000.0, "debit", "shopping", "Croma Store", 3, False, True),
            ]
            for amt, t_type, cat, merch, days, rec, anom in txns:
                db.add(Transaction(
                    account_id="acc-demo-001",
                    amount=amt,
                    transaction_type=t_type,
                    category=cat,
                    merchant_name=merch,
                    transaction_date=now - timedelta(days=days),
                    is_recurring=rec,
                    is_anomalous=anom
                ))

            db.add(PendingAction(
                id="act-001",
                user_id="user-demo-001",
                title="Cap Food Delivery Outflow at INR 6,000/mo",
                rationale="Food delivery expenses (Swiggy + Zomato) are trending 35% above the baseline threshold.",
                suggested_action_type="BUDGET_CAP",
                status="PENDING",
                ai_available=False
            ))
            await db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_if_empty()
    yield

app = FastAPI(title="CashPulse FinTech Agent", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", include_in_schema=False)
async def serve_ui():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "CashPulse Core Backend Active"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "CashPulse"}

@app.get("/api/v1/analytics/runway/{user_id}")
async def get_runway(user_id: str, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    balance = (await db.scalar(select(func.sum(Account.balance)).where(Account.user_id == user_id))) or 0.0
    cutoff = _utcnow() - timedelta(days=30)
    txns = (await db.scalars(
        select(Transaction).join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user_id, Transaction.transaction_date >= cutoff)
        .order_by(desc(Transaction.transaction_date))
    )).all()

    inflow = sum(t.amount for t in txns if t.transaction_type == "credit")
    burn = sum(t.amount for t in txns if t.transaction_type == "debit")
    recurring = sum(t.amount for t in txns if t.is_recurring and t.transaction_type == "debit")
    daily_burn = burn / 30.0 if burn > 0 else 0.0
    runway_days = round(balance / daily_burn, 1) if daily_burn > 0 else 999.0

    return {
        "user_id": user_id,
        "current_balance": round(balance, 2),
        "inflow_30d": round(inflow, 2),
        "burn_30d": round(burn, 2),
        "runway_days": runway_days,
        "recurring_total": round(recurring, 2),
        "anomalies_detected": sum(1 for t in txns if t.is_anomalous),
        "transactions": [
            {"id": t.id, "amount": t.amount, "type": t.transaction_type, "merchant": t.merchant_name, "category": t.category, "is_anomalous": t.is_anomalous}
            for t in txns
        ]
    }

@app.post("/api/v1/transactions")
async def create_transaction(req: TransactionCreate, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, req.account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    ttype = req.transaction_type.lower()
    is_anom = (ttype == "debit" and req.amount > 15000)

    txn = Transaction(
        account_id=req.account_id,
        amount=req.amount,
        transaction_type=ttype,
        category=req.category.lower(),
        merchant_name=req.merchant_name,
        is_recurring=req.is_recurring,
        is_anomalous=is_anom
    )
    account.balance += req.amount if ttype == "credit" else -req.amount
    db.add(txn)
    await db.commit()
    return {"message": "Transaction recorded", "new_balance": round(account.balance, 2), "anomalous": is_anom}

@app.post("/api/v1/simulations/run")
async def run_simulation(req: ScenarioRequest, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, req.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    balance = (await db.scalar(select(func.sum(Account.balance)).where(Account.user_id == req.user_id))) or 0.0
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    explanation = f"Deterministic model: Based on balance of INR {balance:,.0f}, scenario '{req.scenario_description}' introduces liquidity risk."
    gap = 8500.0
    risk = "HIGH" if balance < 50000 else "MEDIUM"
    ai_used = False

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"Balance: INR {balance}. Scenario: {req.scenario_description}. Return JSON: explanation, monthly_gap, risk (LOW/MEDIUM/HIGH/CRITICAL)."
            resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            data = json.loads(resp.text.replace("```json", "").replace("```", "").strip())
            explanation = data.get("explanation", explanation)
            gap = float(data.get("monthly_gap", gap))
            risk = data.get("risk", risk)
            ai_used = True
        except Exception:
            pass

    action = PendingAction(
        user_id=req.user_id,
        title=f"Mitigate: {req.scenario_description[:35]}",
        rationale=explanation,
        suggested_action_type="BUDGET_CAP",
        status="PENDING",
        ai_available=ai_used
    )
    db.add(action)
    await db.commit()
    await db.refresh(action)

    return {
        "scenario": req.scenario_description,
        "monthly_gap_inr": gap,
        "risk_level": risk,
        "explanation": explanation,
        "ai_available": ai_used,
        "action_id": action.id
    }

@app.get("/api/v1/actions/pending/{user_id}")
async def list_pending_actions(user_id: str, db: AsyncSession = Depends(get_db)):
    return (await db.scalars(
        select(PendingAction).where(PendingAction.user_id == user_id, PendingAction.status == "PENDING")
    )).all()

@app.post("/api/v1/actions/{action_id}/decide")
async def decide_action(action_id: str, body: DecisionRequest, db: AsyncSession = Depends(get_db)):
    action = await db.get(PendingAction, action_id)
    if not action:
        raise HTTPException(404, "Action not found")
    action.status = body.decision.upper()
    await db.commit()
    return {"action_id": action.id, "status": action.status}
