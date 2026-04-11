import asyncio
import base64
import json

import sounddevice as sd
import websockets
import numpy as np

from env import *
from tools import TOOLS
from tool_handlers import execute_tool, push_system_prompt


URL = "wss://agents.assemblyai.com/v1/realtime"

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"

MAX_RETRIES = 10
BACKOFF_BASE = 1    # seconds
BACKOFF_CAP = 60    # seconds


async def run_session(ws, speaker, mic_queue, session_ready):
    """Manages one WebSocket session. Returns normally on clean exit (CancelledError).
    Lets ConnectionClosed propagate so the outer loop can retry."""

    # Send session config immediately on connect — before session.ready
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "greeting": "Hi! How can I help?",
            "tools": TOOLS,
        }
    }))
    await push_system_prompt(ws)

    pending_tools: list[dict] = []

    async def send_audio():
        try:
            while True:
                chunk = await mic_queue.get()
                await ws.send(json.dumps({
                    "type": "input.audio",
                    "audio": base64.b64encode(chunk).decode()
                }))
        except (websockets.exceptions.ConnectionClosed, asyncio.CancelledError):
            pass

    send_task = asyncio.create_task(send_audio())

    try:
        async for message in ws:
            event = json.loads(message)
            t = event.get("type")

            if t == "session.ready":
                print(f"Ready — start speaking  (session_id={event.get('session_id', '')})")
                session_ready.set()

            elif t == "session.updated":
                print("Session updated.")

            elif t == "input.speech.started":
                print("\rListening...                    ")

            elif t == "input.speech.stopped":
                print("Processing...")

            elif t == "transcript.user.delta":
                print(f"\rYou: {event['text']}...", end="", flush=True)

            elif t == "transcript.user":
                print(f"\rYou: {event['text']}      ")

            elif t == "reply.started":
                print("Agent speaking...")

            elif t == "transcript.agent":
                print(f"Agent: {event['text']}")

            elif t == "tool.call":
                # Accumulate tool results — send them after reply.done
                pending_tools.append(await execute_tool(event, ws))

            elif t == "reply.audio":
                pcm = np.frombuffer(base64.b64decode(event["data"]), dtype=np.int16)
                speaker.write(pcm)

            elif t == "reply.done":
                if event.get("status") == "interrupted":
                    speaker.abort()   # discard buffered audio immediately
                    speaker.start()   # restart stream for next response
                    pending_tools.clear()
                elif pending_tools:
                    # Send all accumulated tool results
                    for tool in pending_tools:
                        await ws.send(json.dumps({
                            "type": "tool.result",
                            "call_id": tool["call_id"],
                            "result": json.dumps(tool["result"]),
                        }))
                    pending_tools.clear()

            elif t in ("error", "session.error"):
                print(f"Error: {event.get('message')}")
                if t == "error":
                    break

    except asyncio.CancelledError:
        pass  # clean exit — do not propagate, let finally run
    # ConnectionClosed is NOT caught here — surfaces to outer loop as retry signal
    finally:
        send_task.cancel()
        try:
            await send_task
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            pass


async def main():
    headers = {"Authorization": f"Bearer {API_KEY}"}
    loop = asyncio.get_running_loop()
    mic_queue = asyncio.Queue()
    session_ready = asyncio.Event()

    def mic_callback(indata, *_):
        # Only send audio after session.ready fires
        if session_ready.is_set():
            loop.call_soon_threadsafe(mic_queue.put_nowait, bytes(indata))

    attempt = 0

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype=DTYPE, callback=mic_callback), \
         sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                         dtype=DTYPE) as speaker:

        while attempt <= MAX_RETRIES:
            # Reset shared state before each connection attempt
            session_ready.clear()
            while not mic_queue.empty():
                mic_queue.get_nowait()

            # Clear any stale audio in the speaker buffer on reconnect
            if attempt > 0:
                speaker.abort()
                speaker.start()

            try:
                async with websockets.connect(URL, additional_headers=headers) as ws:
                    await run_session(ws, speaker, mic_queue, session_ready)
                break  # run_session returned normally — clean exit

            except asyncio.CancelledError:
                print("\nInterrupted. Exiting.")
                break

            except (websockets.exceptions.ConnectionClosed, OSError) as e:
                attempt += 1
                if attempt > MAX_RETRIES:
                    print(f"Connection lost ({e}). Max retries ({MAX_RETRIES}) reached. Exiting.")
                    break
                delay = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)
                print(f"Connection lost ({e}). Retry {attempt}/{MAX_RETRIES} in {delay:.0f}s...")
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    print("\nInterrupted during backoff. Exiting.")
                    break


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
