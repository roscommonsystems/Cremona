# WebSocket
URL = "wss://agents.assemblyai.com/v1/realtime"

# Audio
SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"

# Sound file paths for audio alerts
SOUND_OPEN = "assets/cremona-open.wav"
SOUND_ERROR = "assets/cremona-error.wav"
SOUND_WAITING = "assets/cremona-waiting.wav"

# Session
GREETING = "Hi! How can I help?"
DEFAULT_VOICE = "kai"

# Reconnection
MAX_RETRIES = 4
BACKOFF_BASE = 1    # seconds
BACKOFF_CAP = 60    # seconds

# Inactivity
INACTIVITY_TIMEOUT = 15 * 60  # seconds

# Memory
MEMORIES_FILE_PATH = "data/memories.json"
MAX_MEMORIES = 10

# Voices
VOICE_DESCRIPTIONS = {
    "alexei": "Russian male",
    "alexis": "American girl",
    "andy": "stoned college kid male",
    "anna": "pleasant American female, hippy",
    "antoine": "French young male",
    "audrey": "mature neutral accent female, dramatic",
    "brian": "young American boy",
    "claire": "American girl, upbeat and friendly",
    "dawn": "soft-voiced American female",
    "diana": "refined mature elegant female",
    "dylan": "straightforward middle-aged American male",
    "gautam": "Indian male, slow-paced",
    "grace": "mysterious dramatic mature woman",
    "jennie": "dainty delicate young female",
    "josh": "neutral middle-aged American male",
    "kai": "ditzy California female",
    "kenji": "confident male with Japanese accent",
    "kevin": "clear casual neutral conversational male",
    "leo": "deep male with Italian/Portuguese accent",
    "lily": "cultured academic female",
}
VOICE_LIST = list(VOICE_DESCRIPTIONS.keys())

# Image generation config (google/gemini-2.5-flash-image)
# Aspect ratio options: "1:1" (1024x1024), "2:3" (832x1248), "3:2" (1248x832),
#   "3:4" (864x1184), "4:3" (1184x864), "4:5" (896x1152), "5:4" (1152x896),
#   "9:16" (768x1344), "16:9" (1344x768), "21:9" (1536x672)
IMAGE_ASPECT_RATIO = "1:1"

# Image size options: "1K" (standard), "2K" (higher), "4K" (highest)
#   "0.5K" is only supported by google/gemini-3.1-flash-image-preview
IMAGE_SIZE = "1K"

# Security
# NOTE: These limits are per-instance. With multiple Cloud Run instances,
# each instance enforces its own limits independently. Set MAX_CONCURRENT_SESSIONS
# to (desired_global_cap / max_instances) to control total load.
# All values can be overridden via environment variables without code changes.
import os as _os
MAX_CONCURRENT_SESSIONS = int(_os.environ.get("MAX_CONCURRENT_SESSIONS", "10"))
MAX_SESSIONS_PER_IP     = int(_os.environ.get("MAX_SESSIONS_PER_IP", "2"))
MAX_WS_MESSAGE_BYTES    = int(_os.environ.get("MAX_WS_MESSAGE_BYTES", str(512 * 1024)))  # 512KB — ~100s of audio in one frame is abnormal
WS_RATE_LIMIT_COUNT     = int(_os.environ.get("WS_RATE_LIMIT_COUNT", "5"))
WS_RATE_LIMIT_WINDOW    = int(_os.environ.get("WS_RATE_LIMIT_WINDOW_SECONDS", "60"))
