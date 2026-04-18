import asyncio
import base64
import datetime
import json
import random

import sounddevice as sd
import numpy as np
import websockets

from env import *
from globals import *

# API_KEY = "YOUR_API_KEY"
URL = "wss://agents.assemblyai.com/v1/realtime"

SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"

TOOLS = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"}
            },
            "required": ["location"]
        }
    },
    {
        "type": "function",
        "name": "get_time",
        "description": "Get the current time and date.",
        "parameters": {"type": "object", "properties": {}}
    },
]

async def execute_tool(event: dict) -> dict:
    name = event.get("name", "")
    args = event.get("args", {})

    if name == "get_weather":
        result = {
            "location": args.get("location", "Unknown"),
            "temp_c": random.randint(5, 28),
            "description": random.choice(["Sunny", "Partly cloudy", "Light rain"]),
        }
    elif name == "get_time":
        now = datetime.datetime.now()
        result = {"time": now.strftime("%I:%M %p"), "date": now.strftime("%A, %B %d")}
    else:
        result = {"error": f"Unknown tool: {name}"}

    return {"call_id": event.get("call_id", ""), "result": result}

async def main():
    headers = {"Authorization": f"Bearer {API_KEY}"}
    async with websockets.connect(URL, additional_headers=headers) as ws:

        # Send session config immediately on connect — before session.ready
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "system_prompt": (
                    "You are a voice assistant. Keep responses to 1-2 short sentences. "
                    "Use your tools for weather and time questions."
                ),
                "voice": "claire",
                "greeting": "Hi! How can I help?",
                "tools": TOOLS,
            }
        }))

        loop = asyncio.get_running_loop()
        mic_queue = asyncio.Queue()
        session_ready = asyncio.Event()
        pending_tools: list[dict] = []

        def mic_callback(indata, *_):
            # Only send audio after session.ready fires
            if session_ready.is_set():
                loop.call_soon_threadsafe(mic_queue.put_nowait, bytes(indata))

        async def send_audio():
            while True:
                chunk = await mic_queue.get()
                await ws.send(json.dumps({
                    "type": "input.audio",
                    "audio": base64.b64encode(chunk).decode()
                }))

        asyncio.create_task(send_audio())

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                            dtype=DTYPE, callback=mic_callback), \
             sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                             dtype=DTYPE) as speaker:

            async for message in ws:
                event = json.loads(message)
                t = event.get("type")

                if t == "session.ready":
                    print(f"Ready — start speaking  (session_id={event.get('session_id', '')})")
                    session_ready.set()

                elif t == "input.speech.started":
                    print("Listening...")

                elif t == "input.speech.stopped":
                    print("Processing...")

                elif t == "transcript.user":
                    print(f"You: {event['text']}")

                elif t == "transcript.agent":
                    print(f"Agent: {event['text']}")

                elif t == "tool.call":
                    # Accumulate tool results — send them after reply.done
                    pending_tools.append(await execute_tool(event))

                elif t == "reply.audio":
                    pcm = np.frombuffer(base64.b64decode(event["data"]), dtype=np.int16)
                    speaker.write(pcm)

                elif t == "reply.done":
                    if event.get("status") == "interrupted":
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

asyncio.run(main())
