# This is the main file to run for the web app
# Run locally with
# source .venv/Scripts/activate
# hypercorn app:app --bind 0.0.0.0:8080

import asyncio
import json
import logging

import websockets
from quart import Quart, render_template, websocket

from config import API_KEY
from globals import (
    URL, GREETING, DEFAULT_VOICE, MAX_RETRIES, BACKOFF_BASE, BACKOFF_CAP,
    INACTIVITY_TIMEOUT,
)
from image_store import get_image_data_url
from tools import TOOLS
from tool_handlers import execute_tool, push_system_prompt

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Quart(__name__)


@app.route("/")
async def index():
    return await render_template("index.html")


async def _forward_browser_to_aai(browser_ws, aai_ws, session_ready):
    """Read messages from the browser and forward audio to AssemblyAI."""
    try:
        while True:
            raw = await browser_ws.receive()
            msg = json.loads(raw)
            if msg.get("type") == "input.audio" and session_ready.is_set():
                await aai_ws.send(json.dumps(msg))
    except Exception:
        pass


async def _send_to_browser(browser_ws, data):
    """Send a JSON message to the browser WebSocket."""
    try:
        await browser_ws.send(json.dumps(data))
    except Exception:
        pass


async def _process_aai_events(browser_ws, aai_ws, session_ready):
    """Read events from AssemblyAI and process/forward them to the browser."""
    pending_tools: list[dict] = []
    waiting_sound_active = False
    last_activity = asyncio.get_event_loop().time()

    async def inactivity_watchdog():
        nonlocal last_activity
        while True:
            await asyncio.sleep(30)
            if asyncio.get_event_loop().time() - last_activity >= INACTIVITY_TIMEOUT:
                log.info("Inactivity timeout reached, closing session")
                await _send_to_browser(browser_ws, {"type": "session.timeout"})
                await aai_ws.close()
                return

    watchdog_task = asyncio.create_task(inactivity_watchdog())

    try:
        async for message in aai_ws:
            event = json.loads(message)
            t = event.get("type")

            if t == "session.ready":
                session_ready.set()
                await _send_to_browser(browser_ws, {"type": "session.ready", "session_id": event.get("session_id", "")})
                await _send_to_browser(browser_ws, {"type": "sound", "name": "open"})

            elif t == "session.updated":
                pass

            elif t == "input.speech.started":
                last_activity = asyncio.get_event_loop().time()
                await _send_to_browser(browser_ws, {"type": "input.speech.started"})

            elif t == "input.speech.stopped":
                await _send_to_browser(browser_ws, {"type": "input.speech.stopped"})

            elif t == "transcript.user.delta":
                last_activity = asyncio.get_event_loop().time()
                await _send_to_browser(browser_ws, {"type": "transcript.user.delta", "text": event.get("text", "")})

            elif t == "transcript.user":
                last_activity = asyncio.get_event_loop().time()
                await _send_to_browser(browser_ws, {"type": "transcript.user", "text": event.get("text", "")})

            elif t == "reply.started":
                await _send_to_browser(browser_ws, {"type": "reply.started"})

            elif t == "transcript.agent.delta":
                await _send_to_browser(browser_ws, {"type": "transcript.agent.delta", "text": event.get("text", "")})

            elif t == "transcript.agent":
                await _send_to_browser(browser_ws, {"type": "transcript.agent", "text": event.get("text", "")})

            elif t == "tool.call":
                if not waiting_sound_active:
                    waiting_sound_active = True
                    await _send_to_browser(browser_ws, {"type": "sound_loop", "name": "waiting", "action": "start"})
                tool_result = await execute_tool(event, aai_ws)
                # Check if generate_image produced images — retrieve from store and send to browser
                result_data = tool_result.get("result", {})
                if isinstance(result_data, dict) and result_data.get("image_ids"):
                    for image_id in result_data["image_ids"]:
                        img_data_url = get_image_data_url(image_id)
                        if img_data_url:
                            await _send_to_browser(browser_ws, {"type": "image", "data": img_data_url})
                pending_tools.append(tool_result)

            elif t == "reply.audio":
                await _send_to_browser(browser_ws, {"type": "reply.audio", "data": event.get("data", "")})

            elif t == "reply.done":
                if event.get("status") == "interrupted":
                    await _send_to_browser(browser_ws, {"type": "reply.interrupted"})
                    pending_tools.clear()
                else:
                    if pending_tools:
                        for tool in pending_tools:
                            await aai_ws.send(json.dumps({
                                "type": "tool.result",
                                "call_id": tool["call_id"],
                                "result": json.dumps(tool["result"]),
                            }))
                        pending_tools.clear()
                if waiting_sound_active:
                    waiting_sound_active = False
                    await _send_to_browser(browser_ws, {"type": "sound_loop", "name": "waiting", "action": "stop"})

            elif t in ("error", "session.error"):
                log.error(f"AssemblyAI error: {event.get('message')}")
                await _send_to_browser(browser_ws, {"type": "error", "message": event.get("message", "Unknown error")})
                await _send_to_browser(browser_ws, {"type": "sound", "name": "error"})
                if t == "error":
                    break

    except websockets.exceptions.ConnectionClosed as e:
        log.info(f"AssemblyAI WebSocket closed: {e}")
    except Exception as e:
        log.error(f"Error processing AssemblyAI events: {e}")
    finally:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass


@app.websocket("/ws")
async def ws_proxy():
    """WebSocket endpoint — each browser connection gets its own AssemblyAI session."""
    browser_ws = websocket._get_current_object()
    headers = {"Authorization": f"Bearer {API_KEY}"}
    session_ready = asyncio.Event()

    try:
        async with websockets.connect(URL, additional_headers=headers) as aai_ws:
            # Send session config
            await aai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "greeting": GREETING,
                    "voice": DEFAULT_VOICE,
                    "tools": TOOLS,
                }
            }))
            await push_system_prompt(aai_ws)

            # Run browser→AAI and AAI→browser concurrently
            browser_task = asyncio.create_task(
                _forward_browser_to_aai(browser_ws, aai_ws, session_ready)
            )
            aai_task = asyncio.create_task(
                _process_aai_events(browser_ws, aai_ws, session_ready)
            )

            done, pending = await asyncio.wait(
                [browser_task, aai_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except websockets.exceptions.InvalidStatusCode as e:
        log.error(f"Failed to connect to AssemblyAI: {e}")
        await _send_to_browser(browser_ws, {"type": "error", "message": "Failed to connect to voice service"})
    except Exception as e:
        log.error(f"WebSocket proxy error: {e}")
        await _send_to_browser(browser_ws, {"type": "error", "message": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
