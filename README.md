# CashPulse AI — FinTech Risk & Runway Agent
## Bit N Build '26 UP hackathon Submission

# ⚡ CashPulse AI — Autonomous Liquidity & Runway Intelligence Agent

> **Zero-Hallucination Treasury Management & Explainable Risk Simulation for Startups and Individuals.**

---

## 🎯 The Problem

1. **Retrospective Tracking:** Most personal finance tools look backwards, summarizing where capital was lost only after accounts run dry.
2. **LLM Math Hallucination:** Emerging Generative AI finance tools attempt to compute arithmetic directly in prompts, leading to dangerous errors in cash runway projections.
3. **Runaway Autonomous AI:** Fully automated agents risk mutating bank balances or draining liquidity without verifiable human consent.

---

## 💡 The Solution: Split-Brain Architecture

**CashPulse AI** decouples deterministic accounting math from generative stress-testing:

* **0% Hallucination Math Core:** All balances, burn velocities, and runway metrics are strictly computed via SQL aggregates and deterministic Python backend logic.
* **Explainable Shock Simulation (Gemini 2.0 Flash):** Evaluates liquidity against real-world "What-If" scenarios (e.g., loss of a client, sudden medical emergency, rent increases) and returns plain-English risk rationales.
* **Dynamic Cash Collapse Date:** Converts abstract "runway days" into an exact, calendar-projected insolvency deadline.
* **Human-in-the-Loop (HITL) Gate:** The AI model is strictly quarantined in a read-only reasoning sandbox. Proposed budget mitigations are staged in an approval queue and cannot mutate state without explicit, authenticated user sign-off.

---

## 🏗️ Architecture Pipeline

* **Client Layer (UI):** React Single-Page Application with real-time telemetry and inline balance reconciliation.
* **Gateway Core (FastAPI):** Asynchronous Python backend executing deterministic balance calculations, dynamic burn velocity, and anomaly detection.
* **AI Engine (Gemini 2.0 Flash):** Read-only sandbox evaluating liquidity shocks and generating plain-English mitigation plans.
* **Persistence Layer (Supabase PostgREST):** Relational tables with Row-Level Security (`users`, `accounts`, `transactions`, `pending_actions`).
* **Governance Gate (HITL):** Staged approval queue ensuring no state mutation occurs without authenticated user confirmation.

---

## 🚀 Key Features

* **Instant Judge Authentication:** 1-Click bypass login along with standard Supabase JWT email authentication.
* **Direct Liquid Balance Reconciler:** Inline editing for treasury adjustments with auto-generated audit delta ledger rows.
* **Audit-Grade Ledger Sync:** Real-time transaction ingestion with automated 2.5x spending spike anomaly detection.
* **Dynamic Cash Collapse Date:** Live forecasting that recalculates instantly upon inflows, debits, or simulated shocks.
* **Graceful Degradation:** Built-in heuristic fallbacks ensure continuous operation even if external AI APIs experience latency.

---

## 🛠️ Tech Stack

* **Backend:** FastAPI (Python 3.11), Pydantic v2, HTTPX
* **Database & Auth:** Supabase (PostgreSQL, PostgREST API, JWT)
* **AI Model:** Google Gemini 2.0 Flash
* **Frontend:** React 18, Tailwind CSS, Babel Standalone
* **Deployment:** Render Cloud Platform

---

## 🛡️ Security & Zero-Hallucination Guarantees

1. **Quarantined Model Access:** Gemini 2.0 receives summarized financial state and has zero write permissions to mutate ledger rows.
2. **Stateless Operations:** High-throughput PostgREST calls eliminate connection pool exhaustion in serverless environments.
3. **Audit Trail Integrity:** Manual balance overrides automatically generate balancing ledger entries to ensure aggregate math reconciles.
