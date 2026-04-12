# Multi-User Deployment Issues

## Overview

This document describes a critical architectural issue that prevents the speech-to-speech application from safely handling multiple concurrent users when deployed to a multi-instance cloud environment like Google Cloud Run.

**Date Identified:** 2026-04-13

## The Issue

When multiple users connect to the deployed application simultaneously, they share state across sessions due to module-level global variables. This results in:

- **Image Cross-Contamination:** User A's generated images appear on User B's screen
- **Voice Interference:** If one user changes the voice, it affects all other users
- **Memory Leakage:** Personal memories saved by one user are visible to all other users

## Root Cause Analysis

### WebSocket Architecture

The application uses Python's Quart framework with WebSocket endpoints. Each client connection spawns a new `ws_proxy()` coroutine in `app.py`:

```python
@app.websocket("/ws")
async def ws_proxy():
    # Each connection gets its OWN:
    # - browser_ws (WebSocket object)
    # - aai_ws (AssemblyAI connection)
    # - session_ready (asyncio.Event)
    # - Local variables: pending_tools, buffers, etc.
```

**This part is correctly isolated**—each user has their own WebSocket session and AssemblyAI connection.

### The Problem: Shared Tool Handler State

While WebSocket sessions are isolated, the **tool handlers** rely on module-level global variables that are shared across ALL sessions:

<table>
<tr><th>Variable</th><th>Location</th><th>Impact</th></tr>
<tr><td><code>_current_image</code></td><td><code>image_store.py</code></td><td>Single global image slot shared by all users</td></tr>
<tr><td><code>current_voice</code></td><td><code>tool_handlers.py:22</code></td><td>One voice setting for all sessions</td></tr>
<tr><td><code>MEMORIES_FILE_PATH</code></td><td><code>tool_handlers.py</code></td><td>Single JSON file shared by all users</td></tr>
</table>

## Detailed Impact

### Issue 1: Image Store (`image_store.py`)

**Current Implementation:**
```python
# image_store.py
_current_image: dict | None = None  # Module-level global

def store_image(data_url: str, prompt: str) -> None:
    global _current_image
    _current_image = {
        "data_url": data_url,
        "prompt": prompt,
    }

def get_image_data_url() -> str | None:
    if _current_image is None:
        return None
    return _current_image.get("data_url")
```

**What Happens:**
1. User A generates an image → calls `store_image(img_A, "prompt_A")` → `_current_image` now holds img_A
2. User B asks "what's in the current image?" → `describe_current_image` calls `get_image_data_url()` → receives img_A
3. User B edits the image → generates img_B → `store_image(img_B, "edit_B")` → `_current_image` now holds img_B
4. User A's image is silently replaced with User B's edits

**Affected Tools:**
- `generate_image` — stores result in global
- `describe_current_image` — reads from global
- `edit_image` — reads old image, stores new image in global

### Issue 2: Voice Selection (`tool_handlers.py`)

**Current Implementation:**
```python
# tool_handlers.py (line 22)
current_voice = DEFAULT_VOICE  # Module-level global

async def change_voice(args: dict, ws) -> dict:
    global current_voice
    voice = args.get("voice", "")
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {"voice": voice}
    }))
    current_voice = voice  # Updates for ALL sessions
    await push_system_prompt(ws)
    return {"success": True, "voice": voice}
```

**What Happens:**
1. User A sets voice to "kai"
2. User B sets voice to "leo"
3. `current_voice` is now "leo" globally
4. All new system prompts (for ALL users) now reference "leo"

**Note:** The AssemblyAI session itself has per-session voice state, so the actual TTS voice stays correct per-user. But the `current_voice` variable is used in `build_system_prompt()` which affects what the AI "thinks" its voice is.

### Issue 3: Memories (`tool_handlers.py`)

**Current Implementation:**
```python
MEMORIES_FILE_PATH = "data/memories.json"  # Single file

async def create_memory(args: dict, ws) -> dict:
    topic = args.get("memory_topic", "")
    content = args.get("memory_content", "")
    success = save_memory_to_file(topic, content)
    # ...

def save_memory_to_file(memory_topic: str, memory_content: str) -> bool:
    # Always writes to the SAME file
    with open(MEMORIES_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(memories_list, f, indent=2)
```

**What Happens:**
1. User A says "remember my name is Alice" → stored in `memories.json`
2. User B says "remember I work in finance" → added to same `memories.json`
3. Both users' memories appear in the system prompt for BOTH users
4. User A asks "what's my name?" → AI has memories for both Alice AND finance, may get confused

## Files Affected

| File | Responsibility | Issue Present? |
|------|---------------|----------------|
| `app.py` | WebSocket handling, session lifecycle | ✅ Correctly isolated per session |
| `image_store.py` | Image storage | ❌ Global `_current_image` shared |
| `tool_handlers.py` | Tool implementations | ❌ `current_voice` and memory file shared |
| `main.py` | Terminal mode (not web server) | Not applicable |
| `globals.py` | Constants | ✅ Safe (read-only) |
| `tools.py` | Tool schemas | ✅ Safe (read-only) |

## Suggested Fixes

### Option 1: Session-Scoped State (Recommended)

Store session-specific state alongside each WebSocket connection and pass it to tool handlers.

**Implementation Steps:**

1. **Create a Session State Class** (new file `session_state.py`):
```python
from dataclasses import dataclass, field

@dataclass
class SessionState:
    """Holds per-session mutable state."""
    current_voice: str = field(default="kai")
    current_image: dict | None = field(default=None)
    # Per-session memories stored in memory for this session only
    # For persistence, consider session-specific memory files

class SessionStore:
    """Simple registry of session_id → SessionState."""
    def __init__(self):
        self._sessions: dict[str, SessionState] = {}
    
    def get_or_create(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
        return self._sessions[session_id]
    
    def remove(self, session_id: str):
        self._sessions.pop(session_id, None)
```

2. **Modify `app.py`** to create/destroy session state:
```python
from session_state import SessionStore

session_store = SessionStore()

@app.websocket("/ws")
async def ws_proxy():
    browser_ws = websocket._get_current_object()
    # Get AssemblyAI session_id when available
    session_ready = asyncio.Event()
    
    try:
        async with websockets.connect(URL, additional_headers=headers) as aai_ws:
            # ... session ready handling
            session_id = None  # Get from session.ready event
            
            # Each session gets its own state
            session_state = session_store.get_or_create(session_id)
            
            try:
                # Pass session_state through the event processing
                await _process_aai_events(browser_ws, aai_ws, session_ready, session_state)
            finally:
                session_store.remove(session_id)
```

3. **Modify `tool_handlers.py`** to accept session state:
```python
async def change_voice(args: dict, ws, session_state: SessionState) -> dict:
    voice = args.get("voice", "")
    # Update the session-specific voice, not global
    session_state.current_voice = voice
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {"voice": voice}
    }))
    await push_system_prompt(ws, session_state.current_voice)
    return {"success": True, "voice": voice}

async def generate_image(args: dict, ws, session_state: SessionState) -> dict:
    # ... generation logic
    # Store in session-specific image slot
    session_state.current_image = {"data_url": data_url, "prompt": prompt}
    return {"status": "generated", "has_image": True, "prompt": prompt}
```

4. **Create session-scoped memory storage** (optional):
```python
# Instead of data/memories.json, use:
# data/memories/{session_id}.json

def get_memory_path(session_id: str) -> str:
    return f"data/memories/{session_id}.json"
```

**Pros:**
- Clean separation of concerns
- Each session is truly isolated
- Scalable to many concurrent users
- Follows web application best practices

**Cons:**
- Requires significant refactoring of `tool_handlers.py`
- Tool handler signatures change (add `session_state` parameter)
- AssemblyAI session_id may not be available immediately (need to handle before session.ready)

### Option 2: Instance-Level State per Session

Create a class that encapsulates all tool handler state and instantiate one per session.

**Implementation Steps:**

1. **Create a ToolHandler class**:
```python
class ToolHandler:
    def __init__(self):
        self.current_voice = DEFAULT_VOICE
        self.current_image = None
        # Memories could be session-scoped or removed if persistence not needed
    
    async def change_voice(self, args: dict, ws) -> dict:
        # Use self.current_voice instead of global
        pass
    
    async def generate_image(self, args: dict, ws) -> dict:
        # Use self.current_image instead of global
        pass
    
    # ... etc for all handlers

HANDLERS_PER_SESSION = {}  # session_id -> ToolHandler instance

def get_handler(session_id: str) -> ToolHandler:
    if session_id not in HANDLERS_PER_SESSION:
        HANDLERS_PER_SESSION[session_id] = ToolHandler()
    return HANDLERS_PER_SESSION[session_id]
```

2. **Modify `app.py`** to instantiate and use the handler:
```python
async def _process_aai_events(browser_ws, aai_ws, session_ready, session_id):
    handler = get_handler(session_id)
    # ...
    elif t == "tool.call":
        tool_name = event.get("name")
        handler_method = getattr(handler, tool_name, None)
        if handler_method:
            tool_result = await handler_method(event.get("args", {}), aai_ws)
```

**Pros:**
- Object-oriented approach
- Self-contained state per handler
- Easy to track what belongs to whom

**Cons:**
- Major refactoring of `tool_handlers.py` (convert functions to methods)
- Still need session identification
- HTTP client (`openai_client`) remains shared but that's fine

### Option 3: Quick Fix - Store State in WebSocket Object

Use the WebSocket object itself to store per-session state (if Quart supports this).

**Implementation Steps:**

```python
@app.websocket("/ws")
async def ws_proxy():
    browser_ws = websocket._get_current_object()
    
    # Attach session state to the WebSocket object
    browser_ws.session_state = {
        "current_voice": DEFAULT_VOICE,
        "current_image": None,
    }
    
    # Then pass browser_ws to handlers instead of just using it for sending
```

**Note:** This depends on whether the WebSocket object persists across coroutine calls and if it supports arbitrary attribute assignment.

### Option 4: Stateless Design (Drastic)

Remove server-side image/voice/memory storage entirely. Images are immediate-only, voices are session-only (AssemblyAI handles it), and memories are... removed or require explicit user storage.

**Pros:**
- No state to manage
- Naturally multi-user safe
- Simplifies code

**Cons:**
- Loses "current image" functionality (can't describe/edit previous)
- Loses persistent memories
- Feature reduction

## Decision Matrix

| Approach | Effort | Cleanliness | Scalability | Recommendation |
|----------|--------|-------------|-------------|----------------|
| Option 1: Session-scoped state | Medium | High | High | **Recommended** |
| Option 2: Instance-level class | Medium-High | High | High | Good alternative |
| Option 3: WebSocket attributes | Low | Medium | Medium | Quick fix |
| Option 4: Stateless | Low | High | High | If features can be cut |

## Immediate Workarounds (Before Proper Fix)

If you need to deploy before implementing a proper fix:

1. **Restrict to single user:** Configure Cloud Run to only allow 1 concurrent instance (not practical for scaling)

2. **Disable problematic features:** Remove `generate_image`, `describe_current_image`, `edit_image`, and `create_memory` from `TOOLS` in `tools.py`

3. **Accept limitations:** Deploy with known issues, document that only one user should use image features at a time

4. **Shorten session timeout:** Lower `INACTIVITY_TIMEOUT` in `globals.py` to 5 minutes or less to clear state faster (minimal help, but something)

## Testing the Fix

After implementing any fix, verify with:

1. **Concurrent Image Test:**
   - User A generates an image of a "cat"
   - User B generates an image of a "dog"
   - User A asks "describe the current image" → should describe cat, NOT dog

2. **Voice Test:**
   - User A changes voice to "andy"
   - User B changes voice to "diana"
   - Both should have their respective voices

3. **Memory Test:**
   - User A creates memory "My name is Alice"
   - User B creates memory "My name is Bob"
   - Both ask "what's my name" → should get appropriate answers

## Conclusion

The current architecture works perfectly for a single user but contains shared state that causes incorrect behavior for multiple concurrent users. The issue is localized to `image_store.py`, `tool_handlers.py`, and the memory file persistence.

**Recommended next step:** Implement Option 1 (session-scoped state) for a clean, scalable solution that maintains all current features while properly isolating user sessions.
