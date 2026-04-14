# This is the main file to run for the web app
# Run locally with
# source .venv/Scripts/activate
# hypercorn app:app --bind 0.0.0.0:8080

import asyncio
import json
import logging
from datetime import timedelta

import websockets
from quart import Quart, abort, render_template, websocket
from quart_rate_limiter import RateLimiter, rate_limit

from config import API_KEY, OPEN_ROUTER_API_KEY
from globals import (
    URL, GREETING, DEFAULT_VOICE, MAX_RETRIES, BACKOFF_BASE, BACKOFF_CAP,
    INACTIVITY_TIMEOUT, MAX_WS_MESSAGE_BYTES,
)
from image_store import get_image_data_url
from security import (
    get_client_ip_ws,
    check_ws_rate_limit,
    track_session,
    TooManySessions,
    RateLimitExceeded,
)
from tools import TOOLS
from tool_handlers import execute_tool, push_system_prompt

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Quart(__name__)

# Enables the @rate_limit decorator on HTTP routes. Uses in-memory storage
# (MemoryStore by default). Per-instance only — see security.py for details.
RateLimiter(app)


@app.before_serving
async def validate_config():
    """Refuse to start if required API keys are absent.

    config.py uses os.environ.get() which silently returns "" for missing keys.
    This hook makes the failure loud and immediate at startup rather than at
    the first user request.
    """
    if not API_KEY:
        raise RuntimeError("API_KEY environment variable is not set. Refusing to start.")
    if not OPEN_ROUTER_API_KEY:
        raise RuntimeError("OPEN_ROUTER_API_KEY environment variable is not set. Refusing to start.")


@app.after_request
async def add_security_headers(response):
    """Add standard HTTP security headers to every HTTP response.

    These headers only apply to HTTP routes (GET /) — not WebSocket connections.
    CSP is tuned to this app's specific needs:
      - blob:            required for MediaSource/AudioContext blob URLs (agent audio playback)
      - data:            required for base64-encoded generated images sent as data: URIs
      - wss:             permits the browser's WebSocket connection back to this server
      - 'unsafe-inline'  needed for any inline styles in templates/static files
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "media-src blob: 'self'; "
        "connect-src 'self' wss:; "
        "img-src 'self' data:; "
        "frame-ancestors 'none';"
    )
    return response


@app.route("/")
@rate_limit(30, timedelta(minutes=1))  # 30 page loads/min per IP
async def index():
    return await render_template("index.html")


@app.before_websocket
async def ws_connection_guard():
    """Rate limit WebSocket upgrade requests before the connection is accepted.

    This runs before the WebSocket handler, so a rejected request never opens
    an AssemblyAI session and never consumes API quota.

    Aborting here sends an HTTP error on the upgrade handshake — the WebSocket
    is never established and no downstream resources are allocated.
    """
    ip = await get_client_ip_ws()
    try:
        await check_ws_rate_limit(ip)
    except RateLimitExceeded:
        abort(429)  # Too Many Requests


async def _forward_browser_to_aai(browser_ws, aai_ws, session_ready):
    """Read messages from the browser and forward audio to AssemblyAI."""
    try:
        while True:
            raw = await browser_ws.receive()

            # Drop oversized frames — legitimate audio chunks at 24kHz 16-bit mono
            # are ~4.8KB/100ms. Anything over MAX_WS_MESSAGE_BYTES is abnormal.
            if isinstance(raw, (bytes, str)) and len(raw) > MAX_WS_MESSAGE_BYTES:
                log.warning(f"Oversized WebSocket message ({len(raw)} bytes) dropped")
                continue

            msg = json.loads(raw)
            if msg.get("type") == "input.audio" and session_ready.is_set():
                await aai_ws.send(json.dumps(msg))
    except Exception as error:
        log.error(f"Error forwarding browser to AssemblyAI: {error}")


async def _send_to_browser(browser_ws, data):
    """Send a JSON message to the browser WebSocket."""
    try:
        await browser_ws.send(json.dumps(data))
    except Exception as error:
        log.error(f"Error sending to browser WebSocket: {error}")


async def _process_aai_events(browser_ws, aai_ws, session_ready):
    """Read events from AssemblyAI and process/forward them to the browser."""
    pending_tools: list[dict] = []
    waiting_sound_active = False
    last_activity = asyncio.get_event_loop().time()
    user_script_buffer = ""
    agent_script_buffer = ""
    last_agent_text = ""

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
                session_id = event.get("session_id", "")
                print(f"Ready — start speaking  (session_id={session_id})")
                await _send_to_browser(browser_ws, {"type": "session.ready", "session_id": session_id})
                await _send_to_browser(browser_ws, {"type": "sound", "name": "open"})

            elif t == "session.updated":
                print("Session updated.")

            elif t == "input.speech.started":
                last_activity = asyncio.get_event_loop().time()
                print("\rListening...                    ")
                await _send_to_browser(browser_ws, {"type": "input.speech.started"})

            elif t == "input.speech.stopped":
                print("Processing...")
                await _send_to_browser(browser_ws, {"type": "input.speech.stopped"})

            elif t == "transcript.user.delta":
                last_activity = asyncio.get_event_loop().time()
                user_text = event.get("text", "")
                user_script_buffer = user_text
                print(f"\rYou: {user_text}...", end="", flush=True)
                await _send_to_browser(browser_ws, {"type": "transcript.user.delta", "text": user_text})

            elif t == "transcript.user":
                last_activity = asyncio.get_event_loop().time()
                user_text = event.get("text", "")
                user_script_buffer = ""
                print(f"\rYou: {user_text}      ")
                await _send_to_browser(browser_ws, {"type": "transcript.user", "text": user_text})

            elif t == "reply.started":
                print("Agent speaking...")
                await _send_to_browser(browser_ws, {"type": "reply.started"})

            elif t == "transcript.agent.delta":
                agent_text = event.get("text", "")
                agent_script_buffer = agent_script_buffer + agent_text
                print(f"\rAgent: {agent_script_buffer}...", end="", flush=True)
                await _send_to_browser(browser_ws, {"type": "transcript.agent.delta", "text": agent_text})

            elif t == "transcript.agent":
                agent_text = event.get("text", "")
                last_agent_text = agent_text
                agent_script_buffer = ""
                await _send_to_browser(browser_ws, {"type": "transcript.agent", "text": agent_text})

            elif t == "tool.call":
                if not waiting_sound_active:
                    waiting_sound_active = True
                    await _send_to_browser(browser_ws, {"type": "sound_loop", "name": "waiting", "action": "start"})
                tool_result = await execute_tool(event, aai_ws)
                # Check if generate_image or edit_image produced an image
                result_data = tool_result.get("result", {})
                if isinstance(result_data, dict) and result_data.get("has_image"):
                    img_data_url = get_image_data_url()
                    if img_data_url:
                        await _send_to_browser(browser_ws, {"type": "image", "data": img_data_url})
                if isinstance(result_data, dict) and result_data.get("trigger_download"):
                    await _send_to_browser(browser_ws, {"type": "trigger_download"})
                pending_tools.append(tool_result)

            elif t == "reply.audio":
                await _send_to_browser(browser_ws, {"type": "reply.audio", "data": event.get("data", "")})

            elif t == "reply.done":
                if event.get("status") == "interrupted":
                    agent_text = last_agent_text or agent_script_buffer
                    if agent_text:
                        print(f"\rAgent (interrupted): {agent_text}      ")
                    last_agent_text = ""
                    agent_script_buffer = ""
                    await _send_to_browser(browser_ws, {"type": "reply.interrupted"})
                    if pending_tools:
                        for tool in pending_tools:
                            await aai_ws.send(json.dumps({
                                "type": "tool.result",
                                "call_id": tool["call_id"],
                                "result": json.dumps(tool["result"]),
                            }))
                        pending_tools.clear()
                else:
                    if last_agent_text:
                        print(f"\rAgent: {last_agent_text}      ")
                    last_agent_text = ""
                    agent_script_buffer = ""
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
                print(f"Error: {event.get('message')}")
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
    ip = await get_client_ip_ws()

    try:
        # track_session enforces global and per-IP concurrent connection limits.
        # The context manager releases the slot in its finally block, so the count
        # is always decremented correctly even if the session errors or is cancelled.
        async with track_session(ip):
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

    except TooManySessions as e:
        # Send the rejection reason to the browser before the connection closes
        log.warning(f"Session rejected for {ip}: {e}")
        await _send_to_browser(browser_ws, {"type": "error", "message": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
