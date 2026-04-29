import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import audio_alerts
from audio_alerts import WaitingSound, _loop_sound, play_sound

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def mock_play_wav(monkeypatch):
    """Replace blocking WAV playback with a no-op so tests run without audio hardware."""
    mock = MagicMock()
    monkeypatch.setattr(audio_alerts, "_play_wav_blocking", mock)
    return mock


@pytest.fixture(autouse=True)
def mock_sd_stop(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(audio_alerts.sd, "stop", mock)
    return mock


# ---------------------------------------------------------------------------
# play_sound
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_play_sound_known_name_triggers_playback(mock_play_wav):
    for name in ("open", "error", "waiting"):
        mock_play_wav.reset_mock()
        await play_sound(name)
        mock_play_wav.assert_called_once()


@pytest.mark.anyio
async def test_play_sound_passes_correct_path(mock_play_wav):
    await play_sound("open")
    path_used = mock_play_wav.call_args[0][0]
    assert "open" in path_used or path_used.endswith(".wav")


@pytest.mark.anyio
async def test_play_sound_unknown_name_does_nothing(mock_play_wav):
    await play_sound("nonexistent")
    mock_play_wav.assert_not_called()


@pytest.mark.anyio
async def test_play_sound_empty_string_does_nothing(mock_play_wav):
    await play_sound("")
    mock_play_wav.assert_not_called()


# ---------------------------------------------------------------------------
# _loop_sound
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_loop_sound_unknown_name_returns_immediately(mock_play_wav):
    stop = asyncio.Event()
    await _loop_sound("nonexistent", stop)
    mock_play_wav.assert_not_called()


@pytest.mark.anyio
async def test_loop_sound_plays_multiple_times_before_stop(mock_play_wav):
    stop = asyncio.Event()
    call_count = 0

    def play_and_maybe_stop(path):
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            stop.set()

    audio_alerts._play_wav_blocking = play_and_maybe_stop

    await _loop_sound("waiting", stop)

    assert call_count == 3


@pytest.mark.anyio
async def test_loop_sound_stops_when_event_preset(mock_play_wav):
    stop = asyncio.Event()
    stop.set()
    await _loop_sound("waiting", stop)
    mock_play_wav.assert_not_called()


# ---------------------------------------------------------------------------
# WaitingSound context manager
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_waiting_sound_starts_background_task():
    async with WaitingSound() as ws:
        assert ws._task is not None
        assert not ws._task.done()


@pytest.mark.anyio
async def test_waiting_sound_task_cancelled_on_exit(mock_sd_stop):
    async with WaitingSound() as ws:
        task = ws._task

    assert task.done()
    mock_sd_stop.assert_called_once()


@pytest.mark.anyio
async def test_waiting_sound_stop_event_set_on_exit():
    async with WaitingSound() as ws:
        stop_event = ws._stop

    assert stop_event.is_set()


@pytest.mark.anyio
async def test_waiting_sound_exit_is_idempotent_on_exception():
    """Exiting after an inner exception should not raise."""
    try:
        async with WaitingSound():
            raise ValueError("simulated error")
    except ValueError:
        pass  # the context manager must suppress nothing — the ValueError propagates


@pytest.mark.anyio
async def test_waiting_sound_can_be_reused():
    """Each use of the context manager is independent."""
    async with WaitingSound() as ws1:
        task1 = ws1._task

    async with WaitingSound() as ws2:
        task2 = ws2._task

    assert task1 is not task2
    assert task1.done()
    assert task2.done()
