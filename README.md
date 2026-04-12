# Speech-to-Speech Voice Agent

A real-time conversational AI application powered by [AssemblyAI's Voice Agent API](https://www.assemblyai.com/docs/speech-to-speech). Speak into your microphone and hear the agent respond in a synthesized voice — no manual transcription or TTS pipeline needed.

## Features

- **Bidirectional audio streaming** over WebSocket — low-latency speech in, speech out
- **20 voice personalities** to choose from (e.g. Kai, Diana, Leo, Audrey)
- **Tool use** — the agent can tell you the time, switch its own voice, and inspect its source code
- **Persistent memory** — the agent remembers things across sessions (stored in `data/memories.json`)
- **Auto-reconnect** with exponential backoff if the connection drops
- **Inactivity timeout** — session ends automatically after 15 minutes of silence
- **Audio alerts** for session open, errors, and tool execution

## Prerequisites

- Python 3.10+
- A microphone and speakers
- An [AssemblyAI API key](https://www.assemblyai.com/dashboard)

## Setup

1. **Clone the repo**
   ```bash
   git clone <repo-url>
   cd speechtospeech_test
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API key**

   Create a `.env` file in the project root:
   ```
   API_KEY=your_assemblyai_api_key_here
   ```

## Usage

```bash
python main.py
```

Speak naturally — the agent will respond through your speakers. Press `Ctrl+C` to end the session.

## Configuration

Key settings are in [globals.py](globals.py):

| Constant | Default | Description |
|---|---|---|
| `DEFAULT_VOICE` | `"kai"` | Voice used at session start |
| `INACTIVITY_TIMEOUT` | `900` s | Seconds of silence before auto-disconnect |
| `MAX_RETRIES` | `4` | Reconnection attempts on connection drop |
| `BACKOFF_CAP` | `60` s | Maximum delay between reconnection attempts |
| `MAX_MEMORIES` | `10` | Maximum number of stored memories |

### Available Voices

| Name | Description |
|---|---|
| alexei | Russian male |
| alexis | American girl |
| andy | Stoned college kid male |
| anna | Pleasant American female, hippy |
| antoine | French young male |
| audrey | Mature neutral accent female, dramatic |
| brian | Young American boy |
| claire | American girl, upbeat and friendly |
| dawn | Soft-voiced American female |
| diana | Refined mature elegant female |
| dylan | Straightforward middle-aged American male |
| gautam | Indian male, slow-paced |
| grace | Mysterious dramatic mature woman |
| jennie | Dainty delicate young female |
| josh | Neutral middle-aged American male |
| kai | Ditzy California female |
| kenji | Confident male with Japanese accent |
| kevin | Clear casual neutral conversational male |
| leo | Deep male with Italian/Portuguese accent |
| lily | Cultured academic female |

## Project Structure

```
speechtospeech_test/
├── main.py            # Entry point — WebSocket session, audio I/O, event loop
├── tools.py           # Tool schemas (definitions sent to the agent)
├── tool_handlers.py   # Tool implementations (time, memory, voice switching)
├── audio_alerts.py    # WAV playback helpers and waiting-sound context manager
├── globals.py         # Constants and configuration
├── env.py             # .env loader
├── assets/            # Alert sound files (.wav)
├── data/              # Runtime data (memories.json written here)
└── .env               # API key (not committed)
```
