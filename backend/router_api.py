"""
router_api.py — REST API Routes (with observability + security)
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .agent import process_voice_turn, run_agent_turn, synthesize_speech
from .database import db_get_all_orders, db_get_all_tickets, db_get_all_refunds
from .observability import metrics
from .security import (
    check_rate_limit, check_prompt_injection, sanitize_input,
    voice_limiter, text_limiter,
)

import base64

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ── Health ───────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "agent": "ARIA",
        "brand": "NovaMart",
        "models": {
            "stt_llm": "gemini-2.5-flash",
            "tts": "gemini-2.5-flash-preview-tts",
            "realtime": "gemini-2.0-flash-live-001",
        },
    }


# ── Metrics ──────────────────────────────────────────────────

@router.get("/metrics")
async def get_metrics():
    """Live observability dashboard data — latency percentiles, tool counts, error rate."""
    return metrics.snapshot()


# ── Orders / Tickets / Refunds (real DB queries) ─────────────

@router.get("/orders")
async def get_orders():
    """Return all orders from SQLite for the UI sidebar."""
    orders = db_get_all_orders()
    sidebar = [
        {
            "id": o["id"],
            "customer_name": o["customer_name"],
            "status": o["status"],
            "total": o["total"],
            "items_count": sum(i["qty"] for i in o["items"]),
            "item_names": [i["name"] for i in o["items"]],
            "placed_at": o["placed_at"],
            "refundable": o["refundable"],
        }
        for o in orders
    ]
    return {"orders": sidebar}


@router.get("/tickets")
async def get_tickets():
    """Return all support tickets from SQLite."""
    return {"tickets": db_get_all_tickets()}


@router.get("/refunds")
async def get_refunds():
    """Return all refund records from SQLite."""
    return {"refunds": db_get_all_refunds()}


# ── Voice Chat (Classic Pipeline) ────────────────────────────

@router.post("/chat")
async def chat(
    request: Request,
    audio: UploadFile = File(...),
    history: str = Form(default="[]"),
):
    """
    Classic pipeline: audio → Gemini STT → function calling → TTS → JSON response.
    Rate limited: 10 requests/minute per IP.
    """
    check_rate_limit(request, voice_limiter, "/api/chat")

    t_start = time.perf_counter()
    try:
        audio_bytes = await audio.read()
        if len(audio_bytes) < 100:
            raise HTTPException(status_code=400, detail="Audio file too small or empty")

        try:
            history_list = json.loads(history)
        except json.JSONDecodeError:
            history_list = []

        mime_type = audio.content_type or "audio/webm"
        result = await process_voice_turn(audio_bytes, history_list, mime_type)

        duration_ms = (time.perf_counter() - t_start) * 1000
        metrics.record_request(duration_ms, True)
        for tc in result.tool_calls:
            metrics.record_tool(tc.name, tc.duration_ms)

        return JSONResponse({
            "transcript": result.user_transcript,
            "reply": result.reply_text,
            "tool_calls": [
                {"name": tc.name, "args": tc.args, "result": tc.result, "duration_ms": tc.duration_ms}
                for tc in result.tool_calls
            ],
            "audio_b64": result.audio_b64,
            "duration_ms": round(duration_ms, 1),
        })

    except HTTPException:
        raise
    except Exception as exc:
        duration_ms = (time.perf_counter() - t_start) * 1000
        metrics.record_request(duration_ms, False)
        logger.error(f"[/api/chat] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(exc)}")


# ── Text Chat (debug / chips) ────────────────────────────────

@router.post("/text-chat")
async def text_chat(request: Request, payload: dict):
    """
    Text-only chat for quick chips and testing.
    Rate limited: 30 requests/minute per IP.
    Includes prompt injection defense.
    """
    check_rate_limit(request, text_limiter, "/api/text-chat")

    user_text = sanitize_input(payload.get("message", ""))
    if not user_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    check_prompt_injection(user_text)

    history_list = payload.get("history", [])
    t_start = time.perf_counter()

    try:
        reply_text, tool_calls = await run_agent_turn(history_list, user_text)
        audio_bytes = await synthesize_speech(reply_text)
        audio_b64 = base64.b64encode(audio_bytes).decode()

        duration_ms = (time.perf_counter() - t_start) * 1000
        metrics.record_request(duration_ms, True)
        for tc in tool_calls:
            metrics.record_tool(tc.name, tc.duration_ms)

        return {
            "reply": reply_text,
            "tool_calls": [
                {"name": tc.name, "args": tc.args, "result": tc.result, "duration_ms": tc.duration_ms}
                for tc in tool_calls
            ],
            "audio_b64": audio_b64,
            "duration_ms": round(duration_ms, 1),
        }

    except HTTPException:
        raise
    except Exception as exc:
        duration_ms = (time.perf_counter() - t_start) * 1000
        metrics.record_request(duration_ms, False)
        logger.error(f"[/api/text-chat] {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
