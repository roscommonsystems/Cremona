# Cremona - Speech-to-Speech Voice Agent

A real-time conversational AI application powered by [AssemblyAI's Voice Agent API](https://www.assemblyai.com/docs/speech-to-speech). Speak naturally and hear the agent respond in a synthesized voice — no manual transcription or TTS pipeline needed.

## Features

- **Bidirectional audio streaming** over WebSocket — low-latency speech in, speech out
- **20 voice personalities** to choose from (e.g. Kai, Diana, Leo, Audrey)
- **Tool use** — the agent can:
  - Tell you the time
  - Switch its own voice
  - Inspect its source code
  - Create memories about your preferences
  - Generate images from text descriptions
  - Describe currently displayed images
  - Edit existing images
- **Image display** — generated and edited images appear in the web interface
- **Persistent memory** — the agent remembers things across sessions (stored in `data/memories.json`)
- **Auto-reconnect** with exponential backoff if the connection drops
- **Inactivity timeout** — session ends automatically after 15 minutes of silence
- **Audio alerts** for session open, errors, and tool execution

## Prerequisites

- Python 3.10+
- A microphone and speakers (for terminal mode)
- An [AssemblyAI API key](https://www.assemblyai.com/dashboard)
- An [OpenRouter API key](https://openrouter.ai/) (for image generation features)

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
   ```
   API_KEY=your_assemblyai_api_key_here
   OPEN_ROUTER_API_KEY=your_openrouter_api_key_here
   ```

## Usage

### Terminal Mode (Audio I/O)

Run the terminal-based version that uses your microphone and speakers directly:

```bash
python main.py
```

Speak naturally — the agent will respond through your speakers. Press `Ctrl+C` to end the session.

### Web App Mode

Run the web interface for browser-based interaction with image display:

```bash
# Development server
hypercorn app:app --bind 0.0.0.0:8080

# Or use Python directly
python app.py
```

Then open `http://localhost:8080` in your browser. Click the logo to start the session.

The web app supports:
- Audio input/output through the browser
- Image generation and display
- Image editing
- All voice and memory tools

## Configuration

Key settings are in [globals.py](globals.py):

| Constant | Default | Description |
|---|---|---|
| `DEFAULT_VOICE` | `"kai"` | Voice used at session start |
| `INACTIVITY_TIMEOUT` | `900` s | Seconds of silence before auto-disconnect |
| `MAX_RETRIES` | `4` | Reconnection attempts on connection drop |
| `BACKOFF_CAP` | `60` s | Maximum delay between reconnection attempts |
| `MAX_MEMORIES` | `10` | Maximum number of stored memories |
| `IMAGE_ASPECT_RATIO` | `"1:1"` | Aspect ratio for generated images |
| `IMAGE_SIZE` | `"1K"` | Resolution for generated images (1K, 2K, 4K) |

### Image Generation Configuration

Available aspect ratios:
- `1:1` - 1024x1024 (default)
- `2:3` - 832x1248
- `3:2` - 1248x832
- `3:4` - 864x1184
- `4:3` - 1184x864
- `4:5` - 896x1152
- `5:4` - 1152x896
- `9:16` - 768x1344
- `16:9` - 1344x768
- `21:9` - 1536x672

Available sizes:
- `1K` - Standard resolution
- `2K` - Higher resolution
- `4K` - Highest resolution

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
├── main.py            # Entry point for terminal mode — WebSocket session, audio I/O, event loop
├── app.py             # Web application (Quart) — browser-based interface with image support
├── tools.py           # Tool schemas (definitions sent to the agent)
├── tool_handlers.py   # Tool implementations (time, memory, voice, image tools)
├── audio_alerts.py    # WAV playback helpers and waiting-sound context manager
├── image_store.py     # In-memory storage for current image (single image at a time)
├── globals.py         # Constants and configuration
├── config.py          # Environment variable loader
├── assets/            # Alert sound files (.wav)
├── static/            # Web app static files (CSS, JS, images)
│   ├── audio/
│   ├── css/
│   ├── img/
│   └── js/
├── templates/         # HTML templates
│   └── index.html
├── data/              # Runtime data (memories.json written here)
└── .env               # API keys (not committed)
```

## Dependencies

Core:
- `quart` - Async web framework
- `hypercorn` - ASGI server
- `websockets` - WebSocket client
- `python-dotenv` - Environment variable loading
- `requests` - HTTP client for API calls
- `pillow` - Image processing
- `openai` - OpenRouter API client

Terminal mode (optional):
- `sounddevice` - Audio device access
- `numpy` - Audio processing

See `requirements.txt` for version specifications.
