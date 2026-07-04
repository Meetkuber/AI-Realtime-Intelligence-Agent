"""
main.py — FastAPI Application Entry Point
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .database import init_db
from .observability import configure_logging
from .router_api import router as api_router
from .router_ws import router as ws_router

configure_logging(json_mode=False)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("⚠️  GEMINI_API_KEY not set — API calls will fail!")
    else:
        logger.info(f"✅ GEMINI_API_KEY loaded (ends: …{api_key[-4:]})")

    # Initialize SQLite + seed from FakeStore API
    logger.info("🗄️  Initializing database…")
    init_db()

    logger.info("🚀 ARIA Voice Agent ready")
    logger.info("   Classic Pipeline : POST /api/chat")
    logger.info("   Text Chat        : POST /api/text-chat")
    logger.info("   Realtime (Live)  : WS   /ws/realtime")
    logger.info("   Metrics          : GET  /api/metrics")
    logger.info("   DB Records       : GET  /api/orders | /api/tickets | /api/refunds")
    logger.info("   API Docs         : GET  /docs")

    yield

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("🛑 ARIA Voice Agent shutting down")


app = FastAPI(
    title="ARIA — AI Realtime Intelligence Agent",
    description=(
        "Voice/Realtime Customer Support Agent powered by Gemini API. "
        "Features: STT + LLM function calling + TTS + Live API realtime mode. "
        "Real SQLite DB, structured observability, rate limiting, prompt injection defense."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {
        "agent": "ARIA — AI Realtime Intelligence Agent",
        "brand": "NovaMart",
        "version": "2.0.0",
        "docs": "/docs",
        "metrics": "/api/metrics",
    }
