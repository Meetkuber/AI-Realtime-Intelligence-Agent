"""
agent.py — Classic Pipeline (Audio → Gemini → TTS)
============================================================
Implements the step-by-step voice pipeline:
  1. Transcribe audio   →  Gemini 2.5 Flash (multimodal)
  2. Agent reasoning    →  Gemini 2.5 Flash with function calling loop
  3. Synthesize speech  →  Gemini TTS (response_modalities=["audio"])
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from .tools import GEMINI_TOOLS, execute_tool

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Gemini Client (module-level singleton)
# ─────────────────────────────────────────────────────────────
_client: genai.Client | None = None

AGENT_MODEL = "gemini-2.5-flash"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Aoede"  # warm, professional voice

SYSTEM_PROMPT = """You are ARIA, an AI-powered voice customer support agent for NovaMart — 
a premium e-commerce platform. You are helpful, empathetic, efficient, and professional.

Your capabilities:
- Look up order status and details
- Process refunds for eligible orders
- Check loyalty points and tier benefits
- Create support tickets for complex issues
- Escalate to a human agent when needed

Guidelines:
- Keep responses concise and clear (this is a voice conversation)
- Always verify order details before processing refunds
- Be empathetic when customers have issues
- Proactively offer relevant help (e.g., after a refund, mention loyalty points)
- Use natural, conversational language — avoid bullet points in speech
- If you call a tool, incorporate the result naturally into your response

Available demo order IDs: ORD-1234, ORD-5678, ORD-9012, ORD-3456
Available demo customer IDs: CUST-001, CUST-002, CUST-003, CUST-004"""


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable not set")
        _client = genai.Client(api_key=api_key)
    return _client


# ─────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────

@dataclass
class ToolCallRecord:
    name: str
    args: dict
    result: dict
    duration_ms: float


@dataclass
class AgentResponse:
    user_transcript: str
    reply_text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    audio_b64: str | None = None
    total_duration_ms: float = 0.0


# ─────────────────────────────────────────────────────────────
# Step 1 — Transcribe Audio
# ─────────────────────────────────────────────────────────────

async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """
    Send audio to Gemini 2.5 Flash for transcription.
    Gemini is natively multimodal — no separate Whisper/STT model needed.
    """
    client = get_client()

    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

    response = client.models.generate_content(
        model=AGENT_MODEL,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text="Transcribe the following audio exactly as spoken. "
                        "Return ONLY the transcription text, no additional commentary."
                    ),
                    audio_part,
                ],
            )
        ],
    )

    transcript = response.text.strip()
    logger.info(f"[Transcription] {transcript!r}")
    return transcript


# ─────────────────────────────────────────────────────────────
# Step 2 — Agent Reasoning with Function Calling Loop
# ─────────────────────────────────────────────────────────────

async def run_agent_turn(
    history: list[dict],
    user_text: str,
) -> tuple[str, list[ToolCallRecord]]:
    """
    Run one agent turn: user message → Gemini reasoning → optional tool calls → final reply.
    Implements the full agentic loop: keep calling tools until the model gives a text response.

    Returns: (reply_text, tool_call_records)
    """
    client = get_client()
    tool_records: list[ToolCallRecord] = []

    # Build Gemini contents from history + new user message
    contents = _build_contents(history, user_text)

    # Gemini tool config
    tools = [types.Tool(function_declarations=[
        types.FunctionDeclaration(**t) for t in GEMINI_TOOLS
    ])]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools,
        temperature=0.7,
    )

    # Agentic loop — keep going until no more function calls
    max_iterations = 5
    for iteration in range(max_iterations):
        response = client.models.generate_content(
            model=AGENT_MODEL,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Check for function calls
        function_calls = [p for p in parts if p.function_call is not None]

        if not function_calls:
            # No more tool calls — extract final text response
            text_parts = [p.text for p in parts if p.text]
            reply_text = " ".join(text_parts).strip()
            return reply_text, tool_records

        # Execute all function calls in this turn
        tool_responses = []
        for part in function_calls:
            fc = part.function_call
            t0 = time.perf_counter()

            args = dict(fc.args) if fc.args else {}
            result = execute_tool(fc.name, args)

            duration_ms = (time.perf_counter() - t0) * 1000
            tool_records.append(ToolCallRecord(
                name=fc.name,
                args=args,
                result=result,
                duration_ms=round(duration_ms, 2),
            ))

            logger.info(f"[Tool] {fc.name}({args}) → {result}")

            tool_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response=result,
                )
            )

        # Add model's function-call turn + our function-response turn to contents
        contents.append(types.Content(role="model", parts=parts))
        contents.append(types.Content(role="user", parts=tool_responses))

    return "I'm sorry, I encountered an issue processing your request. Please try again.", tool_records


def _build_contents(history: list[dict], user_text: str) -> list[types.Content]:
    """Convert flat history list to Gemini Content objects."""
    contents: list[types.Content] = []
    for msg in history:
        contents.append(types.Content(
            role=msg["role"],
            parts=[types.Part.from_text(text=msg["content"])],
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_text)],
    ))
    return contents


# ─────────────────────────────────────────────────────────────
# Step 3 — Text-to-Speech via Gemini TTS
# ─────────────────────────────────────────────────────────────

async def synthesize_speech(text: str) -> bytes:
    """
    Convert text to speech using Gemini TTS.
    Returns raw PCM audio bytes (24kHz, 16-bit mono).
    We convert to WAV for browser playback.
    """
    client = get_client()

    response = client.models.generate_content(
        model=TTS_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=TTS_VOICE,
                    )
                )
            ),
        ),
    )

    # Extract raw PCM bytes from the response
    audio_data = response.candidates[0].content.parts[0].inline_data.data

    # Wrap raw PCM in a WAV container for browser playback
    wav_bytes = _pcm_to_wav(audio_data, sample_rate=24000, channels=1, sampwidth=2)
    return wav_bytes


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int, channels: int, sampwidth: int) -> bytes:
    """Wrap raw PCM audio in a WAV file header."""
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# Full Pipeline — one call to run everything
# ─────────────────────────────────────────────────────────────

async def process_voice_turn(
    audio_bytes: bytes,
    history: list[dict],
    mime_type: str = "audio/webm",
) -> AgentResponse:
    """
    Full classic pipeline:
    audio_bytes → transcribe → agent reasoning → tool calls → TTS → AgentResponse
    """
    t_start = time.perf_counter()

    # 1. Transcribe
    user_transcript = await transcribe_audio(audio_bytes, mime_type)

    # 2. Agent reasoning + tool calls
    reply_text, tool_calls = await run_agent_turn(history, user_transcript)

    # 3. TTS
    audio_bytes_out = await synthesize_speech(reply_text)
    audio_b64 = base64.b64encode(audio_bytes_out).decode()

    total_ms = (time.perf_counter() - t_start) * 1000

    return AgentResponse(
        user_transcript=user_transcript,
        reply_text=reply_text,
        tool_calls=tool_calls,
        audio_b64=audio_b64,
        total_duration_ms=round(total_ms, 2),
    )

