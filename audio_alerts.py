import asyncio
import wave

import numpy as np
import sounddevice as sd

from globals import SOUND_OPEN, SOUND_ERROR, SOUND_WAITING

_SOUNDS = {
    "open":    SOUND_OPEN,
    "error":   SOUND_ERROR,
    "waiting": SOUND_WAITING,
}


def _play_wav_blocking(path: str) -> None:
    """Read and play a WAV file synchronously."""
    with wave.open(path, "rb") as wf:
        rate = wf.getframerate()
        data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    sd.play(data, samplerate=rate, blocking=True)


async def play_sound(name: str) -> None:
    """Play a named alert sound.
    Flask migration: replace body with `socketio.emit("play_sound", {"name": name})`."""
    path = _SOUNDS.get(name)
    if not path:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _play_wav_blocking, path)


async def _loop_sound(name: str, stop_event: asyncio.Event) -> None:
    path = _SOUNDS.get(name)
    if not path:
        return
    loop = asyncio.get_event_loop()
    while not stop_event.is_set():
        await loop.run_in_executor(None, _play_wav_blocking, path)


class WaitingSound:
    """Async context manager: loops 'waiting' sound on enter, stops cleanly on exit.
    Flask migration: __aenter__ emits 'start_sound', __aexit__ emits 'stop_sound'."""

    def __init__(self):
        self._stop: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    async def __aenter__(self):
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(_loop_sound("waiting", self._stop))
        return self

    async def __aexit__(self, *_):
        if self._stop:
            self._stop.set()
        if self._task:
            await self._task  # wait for current iteration to finish cleanly
