# Running this file doesnt open the server, just terminal interaction.

import asyncio
import base64
import json
import logging

import sounddevice as sd
import websockets
import numpy as np

from env import *
from globals import *

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
from tools import TOOLS
from tool_handlers import execute_tool, push_system_prompt
from audio_alerts import play_sound, WaitingSound


async def run_session(ws, speaker, mic_queue, session_ready, timed_out):
    """Manages one WebSocket session. Returns normally on clean exit (CancelledError).
    Lets ConnectionClosed propagate so the outer loop can retry."""

    # Send session config immediately on connect — before session.ready
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "greeting": GREETING,
            "voice": DEFAULT_VOICE,
            "tools": TOOLS,
        }
    }))
    await push_system_prompt(ws)

    pending_tools: list[dict] = []
    waiting_sound: WaitingSound | None = None
    agent_script_buffer = ""
    last_agent_text = ""
    last_activity = [asyncio.get_event_loop().time()]

    def play_tone(freq=440, duration=0.4, volume=0.3):
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
        wave = (np.sin(2 * np.pi * freq * t) * volume * 32767).astype(np.int16)
        speaker.write(wave)

    async def inactivity_watchdog():
        while True:
            await asyncio.sleep(30)
            if asyncio.get_event_loop().time() - last_activity[0] >= INACTIVITY_TIMEOUT:
                print("\nNo activity detected, closing session...")
                timed_out[0] = True
                try:
                    play_tone(freq=440, duration=0.3)
                    await asyncio.sleep(0.4)
                    play_tone(freq=330, duration=0.5)
                    await asyncio.sleep(0.6)
                except Exception:
                    pass
                await ws.close()
                return

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
    watchdog_task = asyncio.create_task(inactivity_watchdog())

    try:
        async for message in ws:
            event = json.loads(message)
            t = event.get("type")

            if t == "session.ready":
                print(f"Ready — start speaking  (session_id={event.get('session_id', '')})")
                session_ready.set()
                asyncio.create_task(play_sound("open"))

            elif t == "session.updated":
                print("Session updated.")

            elif t == "input.speech.started":
                last_activity[0] = asyncio.get_event_loop().time()
                print("\rListening...                    ")

            elif t == "input.speech.stopped":
                print("Processing...")

            elif t == "transcript.user.delta":
                last_activity[0] = asyncio.get_event_loop().time()
                print(f"\rYou: {event['text']}...", end="", flush=True)

            elif t == "transcript.user":
                last_activity[0] = asyncio.get_event_loop().time()
                print(f"\rYou: {event['text']}      ")

            elif t == "reply.started":
                print("Agent speaking...")

            elif t == "transcript.agent.delta":
                agent_script_buffer += event.get("text", "")
                print(f"\rAgent: {agent_script_buffer}...", end="", flush=True)

            elif t == "transcript.agent":
                last_agent_text = event['text']
                agent_script_buffer = ""

            elif t == "tool.call":
                # Accumulate tool results — send them after reply.done
                if waiting_sound is None:
                    waiting_sound = WaitingSound()
                    await waiting_sound.__aenter__()
                pending_tools.append(await execute_tool(event, ws))

            elif t == "reply.audio":
                pcm = np.frombuffer(base64.b64decode(event["data"]), dtype=np.int16)
                speaker.write(pcm)

            elif t == "reply.done":
                if event.get("status") == "interrupted":
                    text = last_agent_text or agent_script_buffer
                    if text:
                        print(f"\rAgent (interrupted): {text}      ")
                    last_agent_text = ""
                    agent_script_buffer = ""
                    speaker.abort()   # discard buffered audio immediately
                    speaker.start()   # restart stream for next response
                    pending_tools.clear()
                    if waiting_sound is not None:
                        await waiting_sound.__aexit__(None, None, None)
                        waiting_sound = None
                else:
                    if last_agent_text:
                        print(f"\rAgent: {last_agent_text}      ")
                    last_agent_text = ""
                    agent_script_buffer = ""
                    if pending_tools:
                        # Send all accumulated tool results
                        for tool in pending_tools:
                            await ws.send(json.dumps({
                                "type": "tool.result",
                                "call_id": tool["call_id"],
                                "result": json.dumps(tool["result"]),
                            }))
                        pending_tools.clear()
                        if waiting_sound is not None:
                            await waiting_sound.__aexit__(None, None, None)
                            waiting_sound = None

            elif t in ("error", "session.error"):
                print(f"Error: {event.get('message')}")
                if t == "error":
                    await play_sound("error")
                    break

    except asyncio.CancelledError:
        pass  # clean exit — do not propagate, let finally run
    # ConnectionClosed is NOT caught here — surfaces to outer loop as retry signal
    finally:
        send_task.cancel()
        watchdog_task.cancel()
        for task in (send_task, watchdog_task):
            try:
                await task
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

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype=DTYPE, callback=mic_callback), \
             sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                             dtype=DTYPE) as speaker:
            while attempt <= MAX_RETRIES:
                # Reset shared state before each connection attempt
                session_ready.clear()
                timed_out = [False]
                while not mic_queue.empty():
                    mic_queue.get_nowait()

                # Clear any stale audio in the speaker buffer on reconnect
                if attempt > 0:
                    speaker.abort()
                    speaker.start()

                try:
                    async with websockets.connect(URL, additional_headers=headers) as ws:
                        await run_session(ws, speaker, mic_queue, session_ready, timed_out)
                    if timed_out[0]:
                        print("Session ended due to inactivity.")
                        break  # inactivity timeout — do not reconnect
                    break  # run_session returned normally — clean exit

                except asyncio.CancelledError:
                    print("\nInterrupted. Exiting.")
                    break

                except (websockets.exceptions.ConnectionClosed, OSError) as e:
                    attempt += 1
                    await play_sound("error")
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

                except websockets.exceptions.WebSocketException as e:
                    attempt += 1
                    log.error(f"WebSocket error: {e}", exc_info=True)
                    await play_sound("error")
                    if attempt > MAX_RETRIES:
                        print(f"WebSocket error ({e}). Max retries ({MAX_RETRIES}) reached. Exiting.")
                        break
                    delay = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)
                    print(f"WebSocket error ({e}). Retry {attempt}/{MAX_RETRIES} in {delay:.0f}s...")
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        print("\nInterrupted during backoff. Exiting.")
                        break

                except Exception as e:
                    attempt += 1
                    log.error(f"Unexpected error in main loop: {e}", exc_info=True)
                    await play_sound("error")
                    if attempt > MAX_RETRIES:
                        print(f"Unexpected error ({e}). Max retries ({MAX_RETRIES}) reached. Exiting.")
                        break
                    delay = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)
                    print(f"Unexpected error ({e}). Retry {attempt}/{MAX_RETRIES} in {delay:.0f}s...")
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        print("\nInterrupted during backoff. Exiting.")
                        break

    except sd.PortAudioError as e:
        log.error(f"Failed to initialize audio devices: {e}", exc_info=True)
        print(f"Failed to initialize audio devices: {e}")
        print("Please check your microphone and speaker are connected and available.")
        return


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
except Exception as e:
    log.error(f"Fatal error: {e}", exc_info=True)
    print(f"\nFatal error: {e}")
