# AssemblyAI Voice Agent API — Full Reference

> Fetched 2026-04-25 from https://www.assemblyai.com/docs/voice-agents/voice-agent-api/
> Pages: session-configuration, voices, audio-format, tool-calling, browser-integration, events-reference

---

## Session Configuration

Send a `session.update` as your first WebSocket message — and any time after — to control how the agent speaks, listens, and responds.

```json
{
  "type": "session.update",
  "session": {
    "system_prompt": "You are a concise support agent. Max 2 sentences per turn.",
    "greeting": "Hi! How can I help you today?",
    "output": { "voice": "emma" },
    "input": {
      "turn_detection": { "type": "server_vad", "vad_threshold": 0.5 }
    }
  }
}
```

Every field is optional — include only what you want to set or change.

### System Prompt

Set the agent's personality and behavior. Can be updated mid-session with another `session.update`.

```json
{
  "type": "session.update",
  "session": {
    "system_prompt": "You are a friendly support agent. Keep responses under 2 sentences. Never make up information."
  }
}
```

**Tips for voice-first prompts:**
- Ban specific phrases: `"Never say 'Certainly' or 'Absolutely'"`
- Enforce brevity: `"Max 2 sentences per turn"`
- Tell the agent when to use each tool

### Greeting

What the agent says at the start of the conversation, spoken aloud. If omitted, the agent waits silently for the user to speak first.

### Voice and Audio Format

Choose a voice and configure the input/output audio format under `session.output` and `session.input`. Only PCM16 at 24 kHz is supported today, so the `format` blocks are optional.

```json
{
  "type": "session.update",
  "session": {
    "input": {
      "format": { "encoding": "audio/pcm", "sample_rate": 24000 }
    },
    "output": {
      "voice": "emma",
      "format": { "encoding": "audio/pcm", "sample_rate": 24000 }
    }
  }
}
```

### Turn Detection

Customize turn detection sensitivity and barge-in behavior under `session.input.turn_detection`. All fields are optional.

```json
{
  "type": "session.update",
  "session": {
    "input": {
      "turn_detection": {
        "type": "server_vad",
        "vad_threshold": 0.5
      }
    }
  }
}
```

| Field           | Type   | Default      | Description                                                             |
| --------------- | ------ | ------------ | ----------------------------------------------------------------------- |
| `type`          | string | `server_vad` | Turn detection algorithm. Currently only `server_vad` is supported.     |
| `vad_threshold` | float  | `0.5`        | Turn detection sensitivity (0.0–1.0). Lower = more sensitive to speech. |

---

## Voices

Pick any voice ID and set it on `session.output.voice` in a `session.update`. You can also switch voices mid-conversation.

```json
{
  "type": "session.update",
  "session": {
    "output": { "voice": "emma" }
  }
}
```

### English Voices — US Accent

| Voice      | Accent | Description                           |
| ---------- | ------ | ------------------------------------- |
| `james`    | 🇺🇸   | Conversational, professional, male    |
| `tyler`    | 🇺🇸   | Theatrical, energetic, chatty, jagged |
| `ivy`      | 🇺🇸   | Professional, deliberate, smooth      |
| `autumn`   | 🇺🇸   | Empathetic, aesthetic, conversational |
| `sam`      | 🇺🇸   | Soft, conversational, young           |
| `mia`      | 🇺🇸   | Smooth, conversational, young         |
| `bella`    | 🇺🇸   | High-pitched, chatty                  |
| `david`    | 🇺🇸   | Deep, calming, conversational         |
| `jack`     | 🇺🇸   | Smooth, direct, clear, fast-paced     |
| `kyle`     | 🇺🇸   | Chatty, nasal, expressive             |
| `helen`    | 🇺🇸   | Soft, older, calming                  |
| `martha`   | 🇺🇸   | Southern, older, warm                 |
| `river`    | 🇺🇸   | Slow, calming, ASMR                   |
| `emma`     | 🇺🇸   | Lively, young, conversational         |
| `victor`   | 🇺🇸   | Deep, older                           |
| `eleanor`  | 🇺🇸   | Deeper, older, calming                |

### English Voices — British Accent

| Voice     | Accent | Description                        |
| --------- | ------ | ---------------------------------- |
| `sophie`  | 🇬🇧   | Clear, smooth, instructive, simple |
| `oliver`  | 🇬🇧   | Narrative, conversational          |

### Multilingual Voices

All multilingual voices also speak English and support code-switching.

| Voice    | Language(s)                                 | Description                            |
| -------- | ------------------------------------------- | -------------------------------------- |
| `arjun`  | 🇮🇳 Hindi/Hinglish, 🇺🇸 English           | Conversational                         |
| `ethan`  | 🇨🇳 Mandarin, 🇺🇸 English                 | Conversational, native in both         |
| `dmitri` | 🇷🇺 Russian, 🇺🇸 English                  | Conversational                         |
| `lukas`  | 🇩🇪 German, 🇺🇸 English                   | British accent, conversational, smooth |
| `lena`   | 🇩🇪 German, 🇺🇸 English                   | Conversational, soft                   |
| `pierre` | 🇫🇷 French, 🇺🇸 English                   | Conversational                         |
| `mina`   | 🇰🇷 Korean, 🇺🇸 English                   |                                        |
| `ren`    | 🇯🇵 Japanese, 🇺🇸 English                 |                                        |
| `mei`    | 🇨🇳 Mandarin, 🇺🇸 English                 |                                        |
| `joon`   | 🇰🇷 Korean, 🇺🇸 English                   |                                        |
| `giulia` | 🇮🇹 Italian, 🇺🇸 English                  |                                        |
| `luca`   | 🇮🇹 Italian, 🇺🇸 English                  |                                        |
| `lucia`  | 🇪🇸 Spanish, 🇺🇸 English                  |                                        |
| `hana`   | 🇯🇵 Japanese, 🇺🇸 English                 |                                        |
| `mateo`  | 🇪🇸 Spanish, 🇺🇸 English                  |                                        |
| `diego`  | 🇨🇴 Spanish (Latin American), 🇺🇸 English | Colombian                              |

---

## Audio Format

Both audio you send (microphone → server) and receive (server → speaker) use the same format: **base64-encoded PCM16, mono, 24 kHz**.

Send approximately 50 ms chunks (2,400 bytes) — the server buffers continuously so exact chunk size doesn't matter.

| Property    | Value                                        |
| ----------- | -------------------------------------------- |
| Encoding    | PCM16 (16-bit signed integer, little-endian) |
| Sample rate | 24,000 Hz                                    |
| Channels    | Mono                                         |
| Transport   | **Base64-encoded** (not raw binary)          |

### Playing Output Audio

The server streams `reply.audio` events containing small PCM16 chunks. Write each chunk directly into an audio output buffer:

```python
# ✅ Buffer-based playback
with sd.OutputStream(samplerate=24000, channels=1, dtype="int16") as speaker:
    if event["type"] == "reply.audio":
        pcm = np.frombuffer(base64.b64decode(event["data"]), dtype=np.int16)
        speaker.write(pcm)
```

**Warning:** Don't use sleep-based timing — the OS clock drifts from the hardware clock causing pops and gaps.

### Stopping Playback on Interruption

When the user interrupts, the server sends `reply.done` with `status: "interrupted"`. Flush your output buffer:

```python
if event.get("status") == "interrupted":
    speaker.abort()   # discard buffered audio immediately
    speaker.start()   # restart stream for next response
```

---

## Tool Calling

Define tools in `session.tools`. The agent fires `tool.call` events; you respond with `tool.result` — **but only after `reply.done` completes**.

### Registering Tools

```json
{
  "type": "session.update",
  "session": {
    "tools": [
      {
        "type": "function",
        "name": "get_weather",
        "description": "Get the current weather for a city.",
        "parameters": {
          "type": "object",
          "properties": {
            "location": { "type": "string", "description": "City name, e.g. London" }
          },
          "required": ["location"]
        }
      }
    ]
  }
}
```

You may update `session.tools` mid-session — the new array supersedes the prior one.

### Handling Tool Calls

**Critical:** collect tool results and dispatch them only in the `reply.done` handler — not immediately on `tool.call`. The agent speaks transitional speech while waiting; premature delivery causes timing conflicts.

```python
pending_tools: list[dict] = []

if t == "tool.call":
    name = event["name"]
    args = event.get("args", {})   # args is a plain dict

    if name == "get_weather":
        result = {"temp_c": 22, "description": "Sunny"}
    else:
        result = {"error": "Unknown tool"}

    pending_tools.append({
        "call_id": event["call_id"],
        "result": result,
    })

elif t == "reply.done":
    if event.get("status") == "interrupted":
        pending_tools.clear()   # user barged in — discard
    elif pending_tools:
        for tool in pending_tools:
            await ws.send(json.dumps({
                "type": "tool.result",
                "call_id": tool["call_id"],
                "result": json.dumps(tool["result"]),
            }))
        pending_tools.clear()
```

---

## Browser Integration

Your server calls `GET /v1/token` with your API key to mint a temporary token, then your browser opens the WebSocket with `?token=<token>`. Your API key stays server-side. Each token is single-use.

### 1. Generate a Token on Your Server

```javascript
// server/routes/voice-token.js
router.get("/voice-token", async (_req, res) => {
  const url = new URL("https://agents.assemblyai.com/v1/token");
  url.searchParams.set("expires_in_seconds", "300");
  url.searchParams.set("max_session_duration_seconds", "8640");

  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${process.env.ASSEMBLYAI_API_KEY}` },
  });

  const { token } = await response.json();
  res.json({ token });
});
```

**Parameter constraints:** `expires_in_seconds` must be 1–600. `max_session_duration_seconds` must be 60–10800 (default 10800 = 3 hours).

### 2. Connect from the Browser

```javascript
const { token } = await fetch("/api/voice-token").then((r) => r.json());

const wsUrl = new URL("wss://agents.assemblyai.com/v1/voice");
wsUrl.searchParams.set("token", token);
const ws = new WebSocket(wsUrl);

ws.addEventListener("open", () => {
  ws.send(JSON.stringify({
    type: "session.update",
    session: {
      system_prompt: "You are a helpful voice assistant.",
      greeting: "Hi there! How can I help you today?",
      output: { voice: "claire" },
    },
  }));
});
```

> Fetch a fresh token for every new WebSocket connection — tokens are single-use.

---

## Events Reference

### Client → Server

#### `input.audio`

Stream PCM16 audio to the agent.

```json
{ "type": "input.audio", "audio": "<base64-encoded PCM16>" }
```

#### `session.update`

Configure the session. Send immediately on connect (before `session.ready`). Can be sent mid-conversation.

Full session fields:

| Field                          | Type   | Description                                           |
| ------------------------------ | ------ | ----------------------------------------------------- |
| `session.system_prompt`        | string | Sets the agent's personality and context              |
| `session.greeting`             | string | Spoken aloud at the start of the conversation         |
| `session.input.format`         | object | Input audio format (`encoding`, `sample_rate`)        |
| `session.input.turn_detection` | object | Turn detection config (`type`, `vad_threshold`)       |
| `session.output.voice`         | string | Voice ID for the agent's speech                       |
| `session.output.format`        | object | Output audio format (`encoding`, `sample_rate`)       |
| `session.tools`                | array  | Tool definitions                                      |

#### `session.resume`

Reconnect to an existing session using `session_id` from a previous `session.ready`. Sessions are preserved for 30 seconds after disconnection.

```json
{ "type": "session.resume", "session_id": "sess_abc123" }
```

If the session has expired, the server returns `session.error` with code `session_not_found` or `session_forbidden`.

```python
session_id: str | None = None

async def connect():
    global session_id
    async with websockets.connect(URL, additional_headers={"Authorization": API_KEY}) as ws:
        if session_id:
            await ws.send(json.dumps({"type": "session.resume", "session_id": session_id}))
        else:
            await ws.send(json.dumps({"type": "session.update", "session": {...}}))

        async for raw in ws:
            event = json.loads(raw)
            if event["type"] == "session.ready":
                session_id = event["session_id"]
            elif event["type"] == "session.error" and event["code"] in ("session_not_found", "session_forbidden"):
                session_id = None
```

#### `tool.result`

Send a tool result back. Send in the `reply.done` handler — not immediately in `tool.call`.

```json
{
  "type": "tool.result",
  "call_id": "call_abc123",
  "result": "{\"temp_c\": 22, \"description\": \"Sunny\"}"
}
```

| Field     | Type   | Description                              |
| --------- | ------ | ---------------------------------------- |
| `call_id` | string | The `call_id` from the `tool.call` event |
| `result`  | string | JSON string containing the tool result   |

---

### Server → Client

#### `session.ready`

Session established. Save `session_id` for reconnection. Start sending `input.audio` only after this event.

```json
{ "type": "session.ready", "session_id": "sess_abc123" }
```

#### `session.updated`

Sent after `session.update` is applied successfully.

```json
{ "type": "session.updated" }
```

#### `input.speech.started` / `input.speech.stopped`

VAD detected the user started/stopped speaking.

#### `transcript.user.delta`

Partial real-time transcript of the user's speech.

```json
{ "type": "transcript.user.delta", "text": "What's the weather in" }
```

#### `transcript.user`

Final transcript of the user's utterance.

```json
{ "type": "transcript.user", "text": "What's the weather in Tokyo?", "item_id": "item_abc123" }
```

#### `reply.started`

Agent has begun generating a response.

```json
{ "type": "reply.started", "reply_id": "reply_abc123" }
```

#### `reply.audio`

A chunk of the agent's spoken response as base64 PCM16. Decode and play immediately.

```json
{ "type": "reply.audio", "data": "<base64-encoded PCM16>" }
```

#### `transcript.agent`

Full text of the agent's response, sent after all audio has been delivered.

```json
{
  "type": "transcript.agent",
  "text": "It's currently 22°C and sunny in Tokyo.",
  "reply_id": "reply_abc123",
  "item_id": "item_abc123",
  "interrupted": false
}
```

| Field         | Type    | Description                                                        |
| ------------- | ------- | ------------------------------------------------------------------ |
| `text`        | string  | What the agent said (trimmed to interruption point if interrupted) |
| `reply_id`    | string  | ID of the reply                                                    |
| `item_id`     | string  | Conversation item ID                                               |
| `interrupted` | boolean | `true` if the user interrupted mid-response                        |

#### `reply.done`

Agent has finished speaking.

```json
{ "type": "reply.done" }
{ "type": "reply.done", "status": "interrupted" }
```

`status: "interrupted"` means the user barged in. Discard pending tool results and flush your audio buffer.

#### `tool.call`

Agent wants to call a registered tool. `args` is a plain dict — use directly.

```json
{
  "type": "tool.call",
  "call_id": "call_abc123",
  "name": "get_weather",
  "args": { "location": "Tokyo" }
}
```

#### `session.error`

Session or protocol error.

```json
{ "type": "session.error", "code": "invalid_format", "message": "Invalid message format" }
```

| Code                | Description                                                      |
| ------------------- | ---------------------------------------------------------------- |
| `invalid_format`    | Malformed event (e.g. `input.audio` sent before `session.ready`) |
| `session_not_found` | The `session_id` in `session.resume` does not exist              |
| `session_forbidden` | The `session_id` belongs to a different API key                  |

---

## Interruptions

When the user speaks mid-response, the server stops the agent and emits:
- `reply.done` with `status: "interrupted"`
- `transcript.agent` with `interrupted: true` and `text` trimmed to what was spoken

Discard pending tool results and flush your local output buffer.
