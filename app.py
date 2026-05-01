# This is the main file to run for the web app
# Run locally with
# source .venv/Scripts/activate
# hypercorn app:app --bind 0.0.0.0:8080

# Sofonisba Anguissola - cremona, italy
# Sofonisba Anguissola (also Sophonisba Angussola or Anguisciola; c. 1532 – 16 November 1625) was an Italian Renaissance painter born in Cremona.

import asyncio
import json
import logging
from datetime import timedelta
import websockets
from quart import Quart, abort, render_template, websocket
from quart_rate_limiter import RateLimiter, rate_limit

# User modules
from config import API_KEY, OPEN_ROUTER_API_KEY
from globals import (
    URL, GREETING, DEFAULT_VOICE, VOICE_DESCRIPTIONS, VOICE_LIST,
    MAX_RETRIES, BACKOFF_BASE, BACKOFF_CAP,
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
import tool_handlers
from tool_handlers import execute_tool, get_system_prompt

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
    try:
        return await render_template(
            "index.html",
            voice_descriptions=VOICE_DESCRIPTIONS,
            default_voice=DEFAULT_VOICE,
        )
    except Exception as error:
        logging.debug(f"An error was encountered: {error}")
        raise


@app.before_websocket
async def ws_connection_guard():
    """Rate limit WebSocket upgrade requests before the connection is accepted.

    This runs before the WebSocket handler, so a rejected request never opens
    an AssemblyAI session and never consumes API quota.

    Aborting here sends an HTTP error on the upgrade handshake — the WebSocket
    is never established and no downstream resources are allocated.
    """
    client_ip = await get_client_ip_ws()
    try:
        await check_ws_rate_limit(client_ip)
    except RateLimitExceeded:
        abort(429)  # Too Many Requests


async def _forward_browser_to_aai(browser_ws, assemblyai_ws, session_ready):
    """Read messages from the browser and forward audio to AssemblyAI."""
    try:
        while True:
            raw_message = await browser_ws.receive()

            # Drop oversized frames — legitimate audio chunks at 24kHz 16-bit mono
            # are ~4.8KB/100ms. Anything over MAX_WS_MESSAGE_BYTES is abnormal.
            if isinstance(raw_message, (bytes, str)) and len(raw_message) > MAX_WS_MESSAGE_BYTES:
                log.warning(f"Oversized WebSocket message ({len(raw_message)} bytes) dropped")
                continue

            try:
                message = json.loads(raw_message)
                if message.get("type") == "input.audio" and session_ready.is_set():
                    await assemblyai_ws.send(json.dumps(message))
            except Exception as error:
                logging.debug(f"An error was encountered: {error}")
    except Exception as error:
        log.error(f"Error forwarding browser to AssemblyAI: {error}")


async def _send_to_browser(browser_ws, data):
    """Send a JSON message to the browser WebSocket."""
    try:
        await browser_ws.send(json.dumps(data))
    except Exception as error:
        log.error(f"Error sending to browser WebSocket: {error}")


async def _process_aai_events(browser_ws, assemblyai_ws, session_ready):
    """Read events from AssemblyAI and process/forward them to the browser."""
    pending_tools: list[dict] = []
    waiting_sound_active = False
    last_activity = asyncio.get_event_loop().time()
    user_script_buffer = ""
    last_agent_text = ""

    async def inactivity_watchdog():
        nonlocal last_activity
        while True:
            await asyncio.sleep(30)
            if asyncio.get_event_loop().time() - last_activity >= INACTIVITY_TIMEOUT:
                log.info("Inactivity timeout reached, closing session")
                await _send_to_browser(browser_ws, {"type": "session.timeout"})
                await assemblyai_ws.close()
                return

    watchdog_task = asyncio.create_task(inactivity_watchdog())

    try:
        async for message in assemblyai_ws:
            try:
                event = json.loads(message)
            except Exception as error:
                logging.debug(f"An error was encountered: {error}")
                continue
            event_type = event.get("type")

            if event_type == "session.ready":
                session_ready.set()
                session_id = event.get("session_id", "")
                print(f"Ready — start speaking  (session_id={session_id})")
                await _send_to_browser(browser_ws, {"type": "session.ready", "session_id": session_id})
                await _send_to_browser(browser_ws, {"type": "sound", "name": "open"})

            elif event_type == "session.updated":
                print("Session updated.")

            elif event_type == "input.speech.started":
                last_activity = asyncio.get_event_loop().time()
                print("\rListening...                    ")
                await _send_to_browser(browser_ws, {"type": "input.speech.started"})

            elif event_type == "input.speech.stopped":
                print("Processing...")
                await _send_to_browser(browser_ws, {"type": "input.speech.stopped"})

            elif event_type == "transcript.user.delta":
                last_activity = asyncio.get_event_loop().time()
                user_text = event.get("text", "")
                user_script_buffer = user_text
                print(f"\rYou: {user_text}...", end="", flush=True)
                await _send_to_browser(browser_ws, {"type": "transcript.user.delta", "text": user_text})

            elif event_type == "transcript.user":
                last_activity = asyncio.get_event_loop().time()
                user_text = event.get("text", "")
                user_script_buffer = ""
                print(f"\rYou: {user_text}      ")
                await _send_to_browser(browser_ws, {"type": "transcript.user", "text": user_text})

            elif event_type == "reply.started":
                print("Agent speaking...")
                await _send_to_browser(browser_ws, {"type": "reply.started"})

            elif event_type == "transcript.agent":
                agent_text = event.get("text", "")
                last_agent_text = agent_text
                await _send_to_browser(browser_ws, {"type": "transcript.agent", "text": agent_text})

            elif event_type == "tool.call":
                if not waiting_sound_active:
                    waiting_sound_active = True
                    await _send_to_browser(browser_ws, {"type": "sound_loop", "name": "waiting", "action": "start"})
                tool_result = await execute_tool(event, assemblyai_ws)
                result_data = tool_result.get("result", {})
                is_dict = isinstance(result_data, dict)

                if is_dict and result_data.get("has_image") and (image_data_url := get_image_data_url()):
                    await _send_to_browser(browser_ws, {"type": "image", "data": image_data_url})
                if is_dict and result_data.get("trigger_download"):
                    await _send_to_browser(browser_ws, {"type": "trigger_download"})
                # if is_dict and event.get("name") == "change_voice":
                #     tool_result["voice_update"] = result_data.get("voice")
                pending_tools.append(tool_result)

            elif event_type == "reply.audio":
                await _send_to_browser(browser_ws, {"type": "reply.audio", "data": event.get("data", "")})

            elif event_type == "reply.done":
                interrupted = event.get("status") == "interrupted"

                if interrupted and last_agent_text:
                    print(f"\rAgent (interrupted): {last_agent_text}      ")
                elif last_agent_text:
                    print(f"\rAgent: {last_agent_text}      ")
                last_agent_text = ""

                if interrupted:
                    await _send_to_browser(browser_ws, {"type": "reply.interrupted"})
                    pending_tools.clear()

                for tool in pending_tools:
                    await assemblyai_ws.send(json.dumps({
                        "type": "tool.result",
                        "call_id": tool["call_id"],
                        "result": json.dumps(tool["result"]),
                    }))
                    # if not tool.get("voice_update"):
                    #     continue
                    # new_voice = tool["voice_update"]
                    # tool_handlers.current_voice = new_voice
                    # await assemblyai_ws.send(json.dumps({
                    #     "type": "session.update",
                    #     "session": {
                    #         "output": {"voice": new_voice},
                    #         "system_prompt": get_system_prompt(),
                    #     },
                    # }))
                pending_tools.clear()

                if waiting_sound_active:
                    waiting_sound_active = False
                    await _send_to_browser(browser_ws, {"type": "sound_loop", "name": "waiting", "action": "stop"})

            elif event_type in ("error", "session.error"):
                print(f"Error: {event.get('message')}")
                log.error(f"AssemblyAI error: {event.get('message')}")
                await _send_to_browser(browser_ws, {"type": "error", "message": event.get("message", "Unknown error")})
                await _send_to_browser(browser_ws, {"type": "sound", "name": "error"})
                if event_type == "error":
                    break

    except websockets.exceptions.ConnectionClosed as error:
        log.info(f"AssemblyAI WebSocket closed: {error}")
        await _send_to_browser(browser_ws, {
            "type": "error",
            "message": "Voice service disconnected. Click logo to reconnect.",
        })
    except Exception as error:
        log.error(f"Error processing AssemblyAI events: {error}")
        await _send_to_browser(browser_ws, {
            "type": "error",
            "message": "Voice service error. Click logo to reconnect.",
        })
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
    client_ip = await get_client_ip_ws()
    headers = {"Authorization": f"Bearer {API_KEY}"}
    session_ready = asyncio.Event()

    _valid_voices = set(VOICE_LIST)
    _requested = websocket.args.get("voice", DEFAULT_VOICE)
    voice = _requested if _requested in _valid_voices else DEFAULT_VOICE
    log.info(f"[ws_proxy] query voice={_requested!r} → using={voice!r}")

    # track_session enforces global and per-IP concurrent connection limits.
    # Its finally block releases the slot, so the count is always decremented
    # correctly even if the session errors or is cancelled.
    try:
        async with track_session(client_ip), \
                   websockets.connect(URL, additional_headers=headers) as assemblyai_ws:
            session_payload = {
                "type": "session.update",
                "session": {
                    "system_prompt": get_system_prompt(voice),
                    "greeting": GREETING,
                    "output": {
                        "voice": voice,
                    },
                    "tools": TOOLS,
                }
            }
            log.info(f"[ws_proxy] session.update → {json.dumps(session_payload)}")
            await assemblyai_ws.send(json.dumps(session_payload))

            # Run browser→AAI and AAI→browser concurrently
            browser_task = asyncio.create_task(
                _forward_browser_to_aai(browser_ws, assemblyai_ws, session_ready)
            )
            assemblyai_task = asyncio.create_task(
                _process_aai_events(browser_ws, assemblyai_ws, session_ready)
            )

            done, pending = await asyncio.wait(
                [browser_task, assemblyai_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in pending:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except TooManySessions as error:
        log.warning(f"Session rejected for {client_ip}: {error}")
        await _send_to_browser(browser_ws, {"type": "error", "message": str(error)})
    except websockets.exceptions.InvalidStatusCode as error:
        log.error(f"Failed to connect to AssemblyAI: {error}")
        await _send_to_browser(browser_ws, {"type": "error", "message": "Failed to connect to voice service"})
    except Exception as error:
        log.error(f"WebSocket proxy error: {error}")
        await _send_to_browser(browser_ws, {"type": "error", "message": str(error)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
