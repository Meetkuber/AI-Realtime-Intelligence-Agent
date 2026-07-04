import asyncio
import json
import logging
import os

from fastapi import WebSocket, WebSocketDisconnect
import websockets

from .tools import GEMINI_TOOLS, execute_tool

logger = logging.getLogger(__name__)

MODEL = "models/gemini-2.0-flash-exp"
HOST = "generativelanguage.googleapis.com"
WS_URL = f"wss://{HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"

async def handle_realtime_session(browser_ws: WebSocket):
    await browser_ws.accept()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY is not set.")
        await browser_ws.close(code=1011, reason="API Key missing")
        return

    url = f"{WS_URL}?key={api_key}"

    try:
        async with websockets.connect(url) as gemini_ws:
            logger.info("Connected to Gemini Live API")

            # 1. Send initial setup
            setup_msg = {
                "setup": {
                    "model": MODEL,
                    "systemInstruction": {
                        "parts": [
                            {"text": "You are ARIA, an AI-powered voice customer support agent for NovaMart. Keep responses concise and clear."}
                        ]
                    },
                    "tools": [{"functionDeclarations": GEMINI_TOOLS}]
                }
            }
            await gemini_ws.send(json.dumps(setup_msg))

            # 2. Browser → Gemini loop
            async def browser_to_gemini():
                try:
                    while True:
                        msg = await browser_ws.receive_text()
                        await gemini_ws.send(msg)
                except WebSocketDisconnect:
                    logger.info("Browser disconnected.")
                except Exception as e:
                    logger.error(f"Error in browser_to_gemini: {e}")

            # 3. Gemini → Browser loop
            async def gemini_to_browser():
                try:
                    async for msg in gemini_ws:
                        # Forward everything to the browser
                        await browser_ws.send_text(msg)

                        # Intercept tool calls to execute them on backend
                        data = json.loads(msg)
                        if "toolCall" in data:
                            function_calls = data["toolCall"].get("functionCalls", [])
                            responses = []
                            for fc in function_calls:
                                call_id = fc.get("id")
                                name = fc.get("name")
                                args = fc.get("args", {})
                                
                                logger.info(f"[Live API Tool] {name}({args})")
                                result = execute_tool(name, args)
                                
                                responses.append({
                                    "id": call_id,
                                    "name": name,
                                    "response": {"result": result}
                                })
                            
                            if responses:
                                tool_response_msg = {
                                    "toolResponse": {
                                        "functionResponses": responses
                                    }
                                }
                                await gemini_ws.send(json.dumps(tool_response_msg))

                except Exception as e:
                    logger.error(f"Error in gemini_to_browser: {e}")

            await asyncio.gather(
                browser_to_gemini(),
                gemini_to_browser()
            )

    except Exception as e:
        logger.error(f"WebSocket Proxy Error: {e}", exc_info=True)
    finally:
        try:
            await browser_ws.close()
        except:
            pass
