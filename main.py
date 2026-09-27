import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("CashPulse")
logging.basicConfig(level=logging.INFO)

# Supabase REST Configuration with reliable fallbacks
SUPABASE_URL = (
    os.getenv("SUPABASE_URL") or "https://ztoqlduggsczxyyhmrry.supabase.co"
).rstrip("/")

SUPABASE_ANON_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp0b3FsZHVnZ3Njenh5eWhtcnJ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTA0ODc0MzcsImV4cCI6MjEwNjA2MzQzN30.6j0G79xUAf5n6tw-ipUEcXsMUG2jbBpHUAo7Pfb1wjw"
).strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

app = FastAPI(title="CashPulse FinTech Agent (Supabase REST)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _get_supabase_headers(auth_token: Optional[str] = None) -> dict[str, str]:
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    else:
        headers["Authorization"] = f"Bearer {SUPABASE_ANON_KEY}"
    return headers

# ---------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------
class SignupRequest(BaseModel):
    name: str
    email: str
    password: str = Field(..., min_length=6)
    baseline_income: float = 90000.0

class LoginRequest(BaseModel):
    email: str
    password: str

class TransactionCreate(BaseModel):
    account_id: str
    amount: float = Field(..., gt=0)
    transaction_type: str
    category: str = "general"
    merchant_name: Optional[str] = None
    is_recurring: bool = False

class BalanceUpdateRequest(BaseModel):
    account_id: str
    new_balance: float = Field(..., ge=0)
    reason: Optional[str] = "Manual Balance Override"

class ScenarioRequest(BaseModel):
    user_id: str
    scenario_description: str
    horizon_days: int = 90

class DecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")

# ---------------------------------------------------------
# Root & Static Serving
# ---------------------------------------------------------
@app.get("/", include_in_schema=False)
async def serve_ui():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "CashPulse Core API Active (Supabase REST mode)"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "CashPulse AI",
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_ANON_KEY)
    }

# ---------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------
@app.post("/api/v1/auth/signup")
async def auth_signup(payload: SignupRequest):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(500, "Supabase credentials not configured on server")

    signup_endpoint = f"{SUPABASE_URL}/auth/v1/signup"
    auth_body = {
        "email": payload.email,
        "password": payload.password,
        "data": {"name": payload.name}
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(signup_endpoint, json=auth_body, headers=_get_supabase_headers())
        if res.status_code >= 400:
            error_detail = res.json().get("msg") or res.json().get("error_description") or res.text
            raise HTTPException(res.status_code, f"Supabase Auth Error: {error_detail}")
        auth_data = res.json()

    user_id = auth_data.get("id") or (auth_data.get("user", {}).get("id") if "user" in auth_data else None)
    access_token = auth_data.get("access_token")

    if user_id:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = _get_supabase_headers(access_token)
            
            # Register user record
            await client.post(
                f"{SUPABASE_URL}/rest/v1/users",
                json={
                    "id": user_id,
                    "name": payload.name,
                    "email": payload.email,
                    "baseline_income": payload.baseline_income
                },
                headers=headers
            )
            
            # Create default checking account
            acc_id = f"acc-{user_id[:8]}"
            await client.post(
                f"{SUPABASE_URL}/rest/v1/accounts",
                json={
                    "id": acc_id,
                    "user_id": user_id,
                    "account_type": "checking",
                    "balance": 125000.0,
                    "currency": "INR"
                },
                headers=headers
            )

    return {
        "message": "User registered successfully",
        "user_id": user_id,
        "access_token": access_token
    }

@app.post("/api/v1/auth/login")
async def auth_login(payload: LoginRequest):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(500, "Supabase credentials not configured on server")

    login_endpoint = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    body = {"email": payload.email, "password": payload.password}

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(login_endpoint, json=body, headers=_get_supabase_headers())
        if res.status_code >= 400:
            error_detail = res.json().get("msg") or res.json().get("error_description") or "Invalid credentials"
            raise HTTPException(res.status_code, error_detail)
        token_data = res.json()

    user_info = token_data.get("user", {})
    return {
        "access_token": token_data.get("access_token"),
        "user_id": user_info.get("id"),
        "email": user_info.get("email"),
        "name": user_info.get("user_metadata", {}).get("name", "User")
    }

# ---------------------------------------------------------
# Analytics & Runway Engine
# ---------------------------------------------------------
@app.get("/api/v1/analytics/runway/{user_id}")
async def get_runway(user_id: str, authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    headers = _get_supabase_headers(token)

    async with httpx.AsyncClient(timeout=10.0) as client:
        acc_res = await client.get(
            f"{SUPABASE_URL}/rest/v1/accounts?user_id=eq.{user_id}&select=id,balance",
            headers=headers
        )
        accounts = acc_res.json() if acc_res.status_code == 200 else []
        total_balance = sum(float(a.get("balance", 0.0)) for a in accounts)
        account_ids = [a["id"] for a in accounts]

        txns = []
        if account_ids:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            acc_filter = f"in.({','.join(account_ids)})"
            txn_url = (
                f"{SUPABASE_URL}/rest/v1/transactions?"
                f"account_id={acc_filter}&transaction_date=gte.{cutoff}"
                f"&order=transaction_date.desc&limit=100"
            )
            txn_res = await client.get(txn_url, headers=headers)
            if txn_res.status_code == 200:
                txns = txn_res.json()

    inflow = sum(float(t["amount"]) for t in txns if t.get("transaction_type") == "credit")
    burn = sum(float(t["amount"]) for t in txns if t.get("transaction_type") == "debit")
    recurring = sum(float(t["amount"]) for t in txns if t.get("is_recurring") and t.get("transaction_type") == "debit")
    
    daily_burn = burn / 30.0 if burn > 0 else 0.0
    runway_days = round(total_balance / daily_burn, 1) if daily_burn > 0 else 999.0

    return {
        "user_id": user_id,
        "current_balance": round(total_balance, 2),
        "inflow_30d": round(inflow, 2),
        "burn_30d": round(burn, 2),
        "runway_days": runway_days,
        "recurring_total": round(recurring, 2),
        "anomalies_detected": sum(1 for t in txns if t.get("is_anomalous")),
        "transactions": [
            {
                "id": t.get("id"),
                "amount": float(t.get("amount", 0)),
                "type": t.get("transaction_type"),
                "merchant": t.get("merchant_name"),
                "category": t.get("category"),
                "is_anomalous": t.get("is_anomalous", False)
            }
            for t in txns
        ]
    }

# ---------------------------------------------------------
# Transactions & Liquid Balance Modification
# ---------------------------------------------------------
@app.post("/api/v1/transactions")
async def record_transaction(req: TransactionCreate, authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    headers = _get_supabase_headers(token)

    ttype = req.transaction_type.lower()
    is_anom = (ttype == "debit" and req.amount > 15000.0)

    async with httpx.AsyncClient(timeout=10.0) as client:
        acc_res = await client.get(
            f"{SUPABASE_URL}/rest/v1/accounts?id=eq.{req.account_id}&select=balance",
            headers=headers
        )
        acc_data = acc_res.json()
        if not acc_data:
            raise HTTPException(404, "Target account not found")

        curr_balance = float(acc_data[0].get("balance", 0.0))
        new_balance = curr_balance + req.amount if ttype == "credit" else curr_balance - req.amount

        # Mutate account balance
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/accounts?id=eq.{req.account_id}",
            json={"balance": new_balance},
            headers=headers
        )

        # Ingest record into ledger
        txn_payload = {
            "account_id": req.account_id,
            "amount": req.amount,
            "transaction_type": ttype,
            "category": req.category.lower(),
            "merchant_name": req.merchant_name,
            "is_recurring": req.is_recurring,
            "is_anomalous": is_anom,
            "transaction_date": datetime.now(timezone.utc).isoformat()
        }
        await client.post(f"{SUPABASE_URL}/rest/v1/transactions", json=txn_payload, headers=headers)

    return {"message": "Transaction recorded", "new_balance": round(new_balance, 2), "anomalous": is_anom}

@app.patch("/api/v1/accounts/balance")
async def update_liquid_balance(req: BalanceUpdateRequest, authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    headers = _get_supabase_headers(token)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Check current balance
        acc_res = await client.get(
            f"{SUPABASE_URL}/rest/v1/accounts?id=eq.{req.account_id}&select=balance",
            headers=headers
        )
        acc_data = acc_res.json()
        if not acc_data:
            raise HTTPException(404, "Target account not found")

        old_balance = float(acc_data[0].get("balance", 0.0))
        delta = req.new_balance - old_balance

        # 1. Update account balance directly in database
        patch_res = await client.patch(
            f"{SUPABASE_URL}/rest/v1/accounts?id=eq.{req.account_id}",
            json={"balance": req.new_balance},
            headers=headers
        )
        if patch_res.status_code >= 400:
            raise HTTPException(patch_res.status_code, "Failed to update account balance")

        # 2. Add an audit adjustment entry so ledger reconciliation remains mathematically sound
        if delta != 0:
            txn_payload = {
                "account_id": req.account_id,
                "amount": abs(delta),
                "transaction_type": "credit" if delta > 0 else "debit",
                "category": "adjustment",
                "merchant_name": f"{req.reason} ({'+' if delta > 0 else '-'}₹{abs(delta):,.2f})",
                "is_recurring": False,
                "is_anomalous": False,
                "transaction_date": datetime.now(timezone.utc).isoformat()
            }
            await client.post(f"{SUPABASE_URL}/rest/v1/transactions", json=txn_payload, headers=headers)

    return {
        "message": "Liquid balance updated successfully",
        "old_balance": round(old_balance, 2),
        "new_balance": round(req.new_balance, 2),
        "delta": round(delta, 2)
    }

# ---------------------------------------------------------
# What-If Shock Simulation
# ---------------------------------------------------------
@app.post("/api/v1/simulations/run")
async def run_simulation(req: ScenarioRequest, authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    headers = _get_supabase_headers(token)

    async with httpx.AsyncClient(timeout=10.0) as client:
        acc_res = await client.get(
            f"{SUPABASE_URL}/rest/v1/accounts?user_id=eq.{req.user_id}&select=balance",
            headers=headers
        )
        accounts = acc_res.json() if acc_res.status_code == 200 else []
        balance = sum(float(a.get("balance", 0.0)) for a in accounts)

    explanation = f"Deterministic model: Based on liquid balance of INR {balance:,.0f}, '{req.scenario_description}' introduces liquidity risk."
    gap = 8500.0
    risk = "HIGH" if balance < 50000 else "MEDIUM"
    ai_used = False

    if GEMINI_API_KEY:
        try:
            from google import genai
            client_ai = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                f"Balance: INR {balance}. Scenario shock: {req.scenario_description}. "
                f"Return JSON strictly with keys: explanation, monthly_gap, risk (LOW/MEDIUM/HIGH/CRITICAL)."
            )
            resp = client_ai.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            data = json.loads(resp.text.replace("```json", "").replace("```", "").strip())
            explanation = data.get("explanation", explanation)
            gap = float(data.get("monthly_gap", gap))
            risk = data.get("risk", risk)
            ai_used = True
        except Exception:
            pass

    # Stage proposal into pending actions
    staged_payload = {
        "user_id": req.user_id,
        "title": f"Mitigate: {req.scenario_description[:35]}",
        "rationale": explanation,
        "suggested_action_type": "BUDGET_CAP",
        "status": "PENDING",
        "ai_available": ai_used
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        ins_res = await client.post(
            f"{SUPABASE_URL}/rest/v1/pending_actions",
            json=staged_payload,
            headers=headers
        )
        staged_items = ins_res.json() if ins_res.status_code in [200, 201] else []

    action_id = staged_items[0].get("id") if staged_items else "staged-001"

    return {
        "scenario": req.scenario_description,
        "monthly_gap_inr": gap,
        "risk_level": risk,
        "explanation": explanation,
        "ai_available": ai_used,
        "action_id": action_id
    }

# ---------------------------------------------------------
# HITL Action Approvals
# ---------------------------------------------------------
@app.get("/api/v1/actions/pending/{user_id}")
async def list_pending_actions(user_id: str, authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    headers = _get_supabase_headers(token)

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.get(
            f"{SUPABASE_URL}/rest/v1/pending_actions?user_id=eq.{user_id}&status=eq.PENDING&order=created_at.desc",
            headers=headers
        )
        return res.json() if res.status_code == 200 else []

@app.post("/api/v1/actions/{action_id}/decide")
async def decide_action(action_id: str, body: DecisionRequest, authorization: Optional[str] = Header(None)):
    token = authorization.replace("Bearer ", "") if authorization else None
    headers = _get_supabase_headers(token)

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.patch(
            f"{SUPABASE_URL}/rest/v1/pending_actions?id=eq.{action_id}",
            json={"status": body.decision.upper()},
            headers=headers
        )
        if res.status_code >= 400:
            raise HTTPException(res.status_code, "Unable to record decision")
    return {"action_id": action_id, "status": body.decision.upper()}
