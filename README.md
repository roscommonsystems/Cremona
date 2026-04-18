# Cremona - Speech-to-Speech Voice Agent

A real-time conversational AI application powered by [AssemblyAI's Voice Agent API](https://www.assemblyai.com/docs/speech-to-speech). Speak naturally and hear the agent respond in a synthesized voice — no manual transcription or TTS pipeline needed.

## Features

- **Bidirectional audio streaming** over WebSocket — low-latency speech in, speech out
- **34 voice personalities** to choose from (e.g. Kai, Diana, Leo, Audrey)
- **Tool use** — the agent can:
  - Switch its own voice
  - Inspect its source code
  - Create memories about your preferences
  - Generate images from text descriptions
  - Describe currently displayed images
  - Edit existing images
  - Download images to disk
- **Image display** — generated and edited images appear in the web interface
- **Persistent memory** — the agent remembers things across sessions (stored in `data/memories.json`)
- **Auto-reconnect** with exponential backoff if the connection drops
- **Inactivity timeout** — session ends automatically after 15 minutes of silence
- **Audio alerts** for session open, errors, and tool execution

## Prerequisites

- Python 3.10+
- An [AssemblyAI API key](https://www.assemblyai.com/dashboard)
- An [OpenRouter API key](https://openrouter.ai/) (for image description)
- An [xAI API key](https://x.ai/) (for image generation via Grok Imagine)

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

4. **Configure your API keys**

   Create a `.env` file in the project root:

   ```env
   API_KEY=your_assemblyai_api_key_here
   OPEN_ROUTER_API_KEY=your_openrouter_api_key_here
   X_AI_API_KEY=your_xai_api_key_here
   ```

## Usage

Run the web app:

```bash
# Development server
python app.py

# Production with Hypercorn
hypercorn app:app --bind 0.0.0.0:8080
```

Then open `http://localhost:8080` in your browser. Click the logo to start the session.

### Docker

```bash
docker build -t cremona .
docker run -p 8080:8080 \
  -e API_KEY=your_assemblyai_key \
  -e OPEN_ROUTER_API_KEY=your_openrouter_key \
  -e X_AI_API_KEY=your_xai_key \
  cremona
```

## Configuration

Key settings are in [globals.py](globals.py):

| Constant | Default | Description |
| --- | --- | --- |
| `DEFAULT_VOICE` | `"kai"` | Voice used at session start |
| `INACTIVITY_TIMEOUT` | `900` s | Seconds of silence before auto-disconnect |
| `MAX_RETRIES` | `4` | Reconnection attempts on connection drop |
| `BACKOFF_CAP` | `60` s | Maximum delay between reconnection attempts |
| `MAX_MEMORIES` | `10` | Maximum number of stored memories |
| `IMAGE_ASPECT_RATIO` | `"1:1"` | Aspect ratio for generated images |
| `IMAGE_SIZE` | `"1k"` | Resolution for generated images (1k, 2k) |
| `MAX_CONCURRENT_SESSIONS` | `10` | Global session cap (per instance) |
| `MAX_SESSIONS_PER_IP` | `2` | Per-IP session limit |

All security limits can be overridden via environment variables without code changes.

### Image Generation Configuration

Available aspect ratios: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `9:16`, `16:9`, `2:1`, `1:2`, `20:9`, `9:20`, `auto`

Available sizes: `1k` (standard), `2k` (higher)

### Available Voices

| Name | Description |
| --- | --- |
| **English** | |
| josh | Conversational, professional, American, male |
| dylan | Theatrical, energetic, chatty, jagged |
| dawn | Professional, deliberate, smooth |
| summer | Empathetic, aesthetic, conversational |
| andy | Soft, conversational, young |
| zoe | Smooth, conversational, young |
| alexis | High-pitched, chatty |
| michael | Deep, calming, conversational |
| pete | Smooth, direct, clear, fast-paced |
| brian | Chatty, nasal, expressive |
| diana | Soft, older, calming |
| grace | Southern, older, warm |
| kai | Slow, calming, ASMR |
| claire | Lively, young, conversational |
| nathan | Deep, older |
| audrey | Deeper, older, calming |
| melissa | British, clear, smooth, instructive |
| will | Narrative, British, conversational |
| **Multilingual** | |
| gautam | Hindi/Hinglish + English, conversational |
| luke | Mandarin + English, native in both |
| alexei | Russian + English, conversational |
| max | German + English, British accent, smooth |
| anna | German + English, conversational, soft |
| antoine | French + English, conversational |
| jennie | Korean + English |
| kenji | Japanese + English |
| lily | Mandarin + English |
| kevin | Korean + English |
| nova | Italian + English |
| marco | Italian + English |
| sofia | Spanish + English |
| yuki | Japanese + English |
| santiago | Spanish + English |
| leo | Spanish (Latin American) + English, Colombian |

## Project Structure

```text
speechtospeech_test/
├── app.py             # Main web application (Quart) — WebSocket proxy, browser UI, session management
├── tools.py           # Tool schemas (definitions sent to the agent)
├── tool_handlers.py   # Tool implementations (memory, voice, image tools)
├── audio_alerts.py    # WAV playback helpers and waiting-sound context manager
├── image_store.py     # In-memory storage for current image (single image at a time)
├── globals.py         # Constants and configuration
├── config.py          # Environment variable loader
├── security.py        # Per-IP rate limiting and concurrent session tracking
├── assets/            # Alert sound files (.wav)
├── static/            # Web app static files (CSS, JS, images)
│   ├── audio/
│   ├── css/
│   ├── img/
│   └── js/
├── templates/         # HTML templates
│   └── index.html
├── data/              # Runtime data (memories.json written here)
├── Dockerfile         # Container build config (Python 3.12-slim, Hypercorn)
└── .env               # API keys (not committed)
```

### Test / Example Files

These files are not part of the main application — they are standalone examples:

| File | Purpose |
| --- | --- |
| `main.py` | Terminal audio I/O demo — connects directly with microphone and speakers |
| `quick_start.py` | Minimal API connection example showing basic tool handling |

## Dependencies

Core:

- `quart` - Async web framework
- `hypercorn` - ASGI server
- `websockets` - WebSocket client
- `quart-rate-limiter` - Rate limiting middleware
- `python-dotenv` - Environment variable loading
- `requests` - HTTP client for API calls
- `pillow` - Image processing
- `openai` - SDK used for OpenRouter and xAI APIs

Terminal examples only (optional):

- `sounddevice` - Audio device access
- `numpy` - Audio processing

See `requirements.txt` for version specifications.
