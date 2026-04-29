import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest
import websockets.exceptions

from app import _forward_browser_to_aai, _process_aai_events, app

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakeBrowserWS:
    def __init__(self, *incoming):
        self._incoming = list(incoming)
        self.sent: list[dict] = []

    async def receive(self):
        if self._incoming:
            return self._incoming.pop(0)
        raise asyncio.CancelledError()

    async def send(self, data):
        self.sent.append(json.loads(data))

    def types(self):
        return [m["type"] for m in self.sent]


class FakeAAIWS:
    """Yields a fixed sequence of events then stops."""

    def __init__(self, *events):
        self._events = list(events)
        self.sent: list[dict] = []

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for event in self._events:
            yield json.dumps(event)

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def close(self):
        pass


class ClosingAAIWS:
    """Stays open until close() is called — used for inactivity/timeout tests."""

    def __init__(self):
        self._closed = asyncio.Event()
        self.sent: list[dict] = []

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        await self._closed.wait()
        if False:
            yield  # make Python treat this as an async generator

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def close(self):
        self._closed.set()


# ---------------------------------------------------------------------------
# HTTP route: index + security headers
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_keys():
    with patch("app.API_KEY", "test-key"), \
         patch("app.OPEN_ROUTER_API_KEY", "test-or-key"):
        yield


async def test_index_returns_200(mock_keys):
    async with app.test_client() as client:
        response = await client.get("/")
    assert response.status_code == 200


async def test_security_headers_on_every_response(mock_keys):
    async with app.test_client() as client:
        response = await client.get("/")
    h = response.headers
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    csp = h.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


async def test_csp_allows_websocket_and_media(mock_keys):
    async with app.test_client() as client:
        response = await client.get("/")
    csp = response.headers.get("Content-Security-Policy", "")
    assert "wss:" in csp       # browser WebSocket back to this server
    assert "blob:" in csp      # MediaSource audio playback
    assert "data:" in csp      # base64 generated images


# ---------------------------------------------------------------------------
# _forward_browser_to_aai: audio gating and size enforcement
# ---------------------------------------------------------------------------

async def test_oversized_messages_never_reach_assemblyai():
    from globals import MAX_WS_MESSAGE_BYTES
    big = json.dumps({"type": "input.audio"}) + ("x" * MAX_WS_MESSAGE_BYTES)
    browser_ws = FakeBrowserWS(big)
    aai_ws = FakeAAIWS()
    session_ready = asyncio.Event()
    session_ready.set()

    await _forward_browser_to_aai(browser_ws, aai_ws, session_ready)

    assert aai_ws.sent == []


async def test_audio_is_held_until_session_is_ready():
    msg = json.dumps({"type": "input.audio"})
    browser_ws = FakeBrowserWS(msg)
    aai_ws = FakeAAIWS()
    session_ready = asyncio.Event()  # not set

    await _forward_browser_to_aai(browser_ws, aai_ws, session_ready)

    assert aai_ws.sent == []


async def test_audio_is_forwarded_once_session_is_ready():
    msg = json.dumps({"type": "input.audio"})
    browser_ws = FakeBrowserWS(msg)
    aai_ws = FakeAAIWS()
    session_ready = asyncio.Event()
    session_ready.set()

    await _forward_browser_to_aai(browser_ws, aai_ws, session_ready)

    assert len(aai_ws.sent) == 1
    assert aai_ws.sent[0]["type"] == "input.audio"


# ---------------------------------------------------------------------------
# _process_aai_events: session lifecycle
# ---------------------------------------------------------------------------

async def test_session_ready_sets_event_and_notifies_browser():
    browser_ws = FakeBrowserWS()
    session_ready = asyncio.Event()
    aai_ws = FakeAAIWS({"type": "session.ready", "session_id": "s1"})

    await _process_aai_events(browser_ws, aai_ws, session_ready)

    assert session_ready.is_set()
    assert "session.ready" in browser_ws.types()


async def test_session_ready_plays_open_sound():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS({"type": "session.ready", "session_id": "s1"})

    await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    open_sounds = [m for m in browser_ws.sent if m.get("type") == "sound" and m.get("name") == "open"]
    assert len(open_sounds) == 1


async def test_speech_and_transcript_events_forwarded_to_browser():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS(
        {"type": "input.speech.started"},
        {"type": "input.speech.stopped"},
        {"type": "transcript.user", "text": "hello world"},
        {"type": "transcript.user.delta", "text": "hello"},
    )

    await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    types = browser_ws.types()
    assert "input.speech.started" in types
    assert "input.speech.stopped" in types
    assert "transcript.user" in types
    assert "transcript.user.delta" in types


async def test_user_transcript_text_preserved():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS({"type": "transcript.user", "text": "buy milk"})

    await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    msgs = [m for m in browser_ws.sent if m.get("type") == "transcript.user"]
    assert msgs[0]["text"] == "buy milk"


async def test_agent_transcript_forwarded_to_browser():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS({"type": "transcript.agent", "text": "Here is what I found"})

    await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    msgs = [m for m in browser_ws.sent if m.get("type") == "transcript.agent"]
    assert msgs[0]["text"] == "Here is what I found"


# ---------------------------------------------------------------------------
# _process_aai_events: tool call / reply.done lifecycle
# ---------------------------------------------------------------------------

async def test_waiting_sound_starts_on_first_tool_call():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS(
        {"type": "tool.call", "call_id": "c1", "name": "some_tool"},
        {"type": "reply.done", "status": "complete"},
    )
    with patch("app.execute_tool", new=AsyncMock(return_value={"call_id": "c1", "result": {}})):
        await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    starts = [m for m in browser_ws.sent if m.get("type") == "sound_loop" and m.get("action") == "start"]
    assert len(starts) == 1
    assert starts[0]["name"] == "waiting"


async def test_waiting_sound_starts_only_once_for_back_to_back_tools():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS(
        {"type": "tool.call", "call_id": "c1", "name": "tool_a"},
        {"type": "tool.call", "call_id": "c2", "name": "tool_b"},
        {"type": "reply.done", "status": "complete"},
    )
    results = [{"call_id": "c1", "result": {}}, {"call_id": "c2", "result": {}}]
    with patch("app.execute_tool", new=AsyncMock(side_effect=results)):
        await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    starts = [m for m in browser_ws.sent if m.get("type") == "sound_loop" and m.get("action") == "start"]
    assert len(starts) == 1


async def test_waiting_sound_stops_after_reply_done():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS(
        {"type": "tool.call", "call_id": "c1", "name": "some_tool"},
        {"type": "reply.done", "status": "complete"},
    )
    with patch("app.execute_tool", new=AsyncMock(return_value={"call_id": "c1", "result": {}})):
        await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    stops = [m for m in browser_ws.sent if m.get("type") == "sound_loop" and m.get("action") == "stop"]
    assert len(stops) == 1


async def test_tool_results_submitted_to_assemblyai_on_reply_done():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS(
        {"type": "tool.call", "call_id": "c1", "name": "some_tool"},
        {"type": "reply.done", "status": "complete"},
    )
    with patch("app.execute_tool", new=AsyncMock(return_value={"call_id": "c1", "result": {"answer": 42}})):
        await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    results = [m for m in aai_ws.sent if m.get("type") == "tool.result"]
    assert len(results) == 1
    assert results[0]["call_id"] == "c1"


async def test_interrupted_reply_discards_pending_tools():
    """Tool results must NOT be sent when the reply was interrupted mid-stream."""
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS(
        {"type": "tool.call", "call_id": "c1", "name": "some_tool"},
        {"type": "reply.done", "status": "interrupted"},
    )
    with patch("app.execute_tool", new=AsyncMock(return_value={"call_id": "c1", "result": {}})):
        await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    results = [m for m in aai_ws.sent if m.get("type") == "tool.result"]
    assert results == []


# ---------------------------------------------------------------------------
# _process_aai_events: error handling
# ---------------------------------------------------------------------------

async def test_aai_error_event_sends_error_message_to_browser():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS({"type": "error", "message": "quota exceeded"})

    await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    errors = [m for m in browser_ws.sent if m.get("type") == "error"]
    assert len(errors) == 1
    assert "quota exceeded" in errors[0]["message"]


async def test_aai_error_event_plays_error_sound():
    browser_ws = FakeBrowserWS()
    aai_ws = FakeAAIWS({"type": "error", "message": "oops"})

    await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    sounds = [m for m in browser_ws.sent if m.get("type") == "sound" and m.get("name") == "error"]
    assert len(sounds) == 1


async def test_connection_closed_tells_user_to_reconnect():
    browser_ws = FakeBrowserWS()

    class DroppingAAIWS(FakeAAIWS):
        async def _gen(self):
            raise websockets.exceptions.ConnectionClosed(None, None)
            if False:
                yield

    await _process_aai_events(browser_ws, DroppingAAIWS(), asyncio.Event())

    errors = [m for m in browser_ws.sent if m.get("type") == "error"]
    assert errors, "browser should receive an error message on disconnect"
    combined = " ".join(m["message"] for m in errors).lower()
    assert "reconnect" in combined


async def test_unexpected_server_exception_sends_error_to_browser():
    browser_ws = FakeBrowserWS()

    class CrashingAAIWS(FakeAAIWS):
        async def _gen(self):
            raise RuntimeError("unexpected crash")
            if False:
                yield

    await _process_aai_events(browser_ws, CrashingAAIWS(), asyncio.Event())

    errors = [m for m in browser_ws.sent if m.get("type") == "error"]
    assert errors, "browser should receive an error message on server crash"


# ---------------------------------------------------------------------------
# _process_aai_events: inactivity watchdog
# ---------------------------------------------------------------------------

async def test_inactivity_timeout_sends_session_timeout_to_browser():
    """After a period of silence the browser is told the session timed out."""
    browser_ws = FakeBrowserWS()
    aai_ws = ClosingAAIWS()

    with patch("app.INACTIVITY_TIMEOUT", 0), \
         patch("asyncio.sleep", new=AsyncMock()):
        await _process_aai_events(browser_ws, aai_ws, asyncio.Event())

    assert "session.timeout" in browser_ws.types()
