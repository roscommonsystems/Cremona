> For clean Markdown of any page, append .md to the page URL.
> For a complete documentation index, see https://www.assemblyai.com/docs/voice-agents/llms.txt.
> For full documentation content, see https://www.assemblyai.com/docs/voice-agents/llms-full.txt.

# Voice Agent API

> For the complete documentation index, see [llms.txt](https://www.assemblyai.com/docs/llms.txt)

Stream microphone audio into a single WebSocket and receive the agent's spoken response back in real time — no separate STT, LLM, or TTS services to wire up. Turn detection, tool calling, and barge-in are built in.

**Endpoint:** `wss://agents.assemblyai.com/v1/voice`

Jump to the [Quickstart](#quickstart) below for a complete working agent in \~50 lines, or follow the step-by-step pages in the sidebar to build one from scratch.

***

## Connection

**Endpoint**

```
wss://agents.assemblyai.com/v1/voice
```

**Authentication**

Pass your API key as a Bearer token in the HTTP upgrade request:

```
Authorization: Bearer YOUR_API_KEY
```

For client-side apps (where you can't set custom headers or expose your API key), generate a short-lived [temporary token](/docs/api-reference/voice-agent-api/voice-agent-web-socket/generate-voice-agent-token) on your server and pass it as a query parameter instead:

```
wss://agents.assemblyai.com/v1/voice?token=YOUR_TEMP_TOKEN
```

See [Browser integration](/docs/voice-agents/voice-agent-api/browser-integration) for the full token flow.

### Resuming a session

Sessions are preserved for 30 seconds after every disconnection. Reconnect using `session.resume` with the `session_id` from the previous `session.ready` event to preserve conversation context. See [session.resume](/docs/voice-agents/voice-agent-api/events-reference#sessionresume) for the exact event.

***

## Quickstart

A complete working example — connects to the Voice Agent API, streams microphone audio, plays back the agent's voice, and wires up the [AssemblyAI docs MCP server](/docs/coding-agent-prompts#mcp-server) as a tool. Run it and just talk to the agent to ask any question about the Voice Agent API — no more reading docs.

<Steps>
  <Step title="Get your API key">
    Grab your API key from your [AssemblyAI dashboard](https://www.assemblyai.com/app).
  </Step>

  <Step title="Install dependencies">
    ```bash
    pip install websockets sounddevice numpy mcp
    ```
  </Step>

  <Step title="Run">
    ```python
    import asyncio
    import base64
    import json

    import sounddevice as sd
    import numpy as np
    import websockets

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    API_KEY = "YOUR_API_KEY"
    URL = "wss://agents.assemblyai.com/v1/voice"
    MCP_URL = "https://mcp.assemblyai.com/docs"

    SAMPLE_RATE = 24000
    CHANNELS = 1
    DTYPE = "int16"

    # Expose the AssemblyAI docs MCP tools to the agent.
    TOOLS = [
        {
            "type": "function",
            "name": "search_docs",
            "description": "Search AssemblyAI documentation for any question about the Voice Agent API or other AssemblyAI products.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language search query"}
                },
                "required": ["query"],
            },
        },
        {
            "type": "function",
            "name": "get_pages",
            "description": "Retrieve the full content of specific AssemblyAI documentation pages by path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Documentation page paths returned by search_docs",
                    }
                },
                "required": ["paths"],
            },
        },
    ]

    async def call_mcp_tool(mcp: ClientSession, name: str, args: dict) -> str:
        """Forward a Voice Agent tool call to the AssemblyAI docs MCP server."""
        result = await mcp.call_tool(name, args)
        return "\n".join(c.text for c in result.content if getattr(c, "text", None))

    async def main():
        # Connect to the AssemblyAI docs MCP server and keep the session open for tool calls.
        async with streamablehttp_client(MCP_URL) as (read, write, _), \
                   ClientSession(read, write) as mcp:
            await mcp.initialize()

            headers = {"Authorization": f"Bearer {API_KEY}"}
            async with websockets.connect(URL, additional_headers=headers) as ws:

                # Send session config immediately on connect — before session.ready
                await ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "system_prompt": (
                            "You are an AssemblyAI Voice Agent API expert. "
                            "For any question about AssemblyAI, call search_docs first and, "
                            "if needed, get_pages to read a specific page. "
                            "Answer in 1-3 short sentences based on what the tools return."
                        ),
                        "greeting": "Hey! I can answer questions about the Voice Agent API — what would you like to know?",
                        "output": {"voice": "dawn"},
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
                            # Forward the call to the MCP server, accumulate the result,
                            # and send it back after reply.done
                            try:
                                result = await call_mcp_tool(mcp, event.get("name", ""), event.get("args", {}))
                            except Exception as e:
                                result = f"Error calling MCP tool: {e}"
                            pending_tools.append({"call_id": event.get("call_id", ""), "result": result})

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
                                        "result": tool["result"],
                                    }))
                                pending_tools.clear()

                        elif t in ("error", "session.error"):
                            print(f"Error: {event.get('message')}")
                            if t == "error":
                                break

    asyncio.run(main())
    ```
  </Step>
</Steps>

***

## Event flow

A typical voice agent session moves through the events in this order:

```
Client                              Server
  │                                   │
  │── WebSocket connect ──────────────►│
  │── session.update ─────────────────►│  (system prompt + tools + greeting)
  │                                   │
  │◄─── session.ready ────────────────│  (save session_id)
  │                                   │
  │── input.audio (stream) ──────────►│  (only after session.ready)
  │── input.audio (stream) ──────────►│
  │                                   │
  │◄─── input.speech.started ─────────│
  │◄─── transcript.user.delta ────────│
  │◄─── input.speech.stopped ─────────│
  │◄─── transcript.user ──────────────│
  │                                   │
  │◄─── reply.started ────────────────│
  │◄─── reply.audio ──────────────────│
  │◄─── transcript.agent ─────────────│
  │◄─── reply.done ───────────────────│
  │                                   │
  │  [tool call flow]                 │
  │◄─── tool.call ────────────────────│  (args is a dict)
  │◄─── reply.done ───────────────────│  ← send tool.result here
  │── tool.result ────────────────────►│
  │◄─── reply.started ────────────────│
  │◄─── reply.audio ──────────────────│
  │◄─── reply.done ───────────────────│
```

See the [events reference](/docs/voice-agents/voice-agent-api/events-reference) for every event's full payload.