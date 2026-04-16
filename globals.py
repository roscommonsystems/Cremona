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
    # English voices
    "josh":     "Conversational, professional, American, male",
    "dylan":    "Theatrical, energetic, chatty, jagged",
    "dawn":     "Professional, deliberate, smooth",
    "summer":   "Empathetic, aesthetic, conversational",
    "andy":     "Soft, conversational, young",
    "zoe":      "Smooth, conversational, young",
    "alexis":   "High-pitched, chatty",
    "michael":  "Deep, calming, conversational",
    "pete":     "Smooth, direct, clear, fast-paced",
    "brian":    "Chatty, nasal, expressive",
    "diana":    "Soft, older, calming",
    "grace":    "Southern, older, warm",
    "kai":      "Slow, calming, ASMR",
    "claire":   "Lively, young, conversational",
    "nathan":   "Deep, older",
    "audrey":   "Deeper, older, calming",
    "melissa":  "British, clear, smooth, instructive",
    "will":     "Narrative, British, conversational",
    # Multilingual voices
    "gautam":   "Hindi/Hinglish + English, conversational",
    "luke":     "Mandarin + English, conversational, native in both",
    "alexei":   "Russian + English, conversational",
    "max":      "German + English, British accent, smooth",
    "anna":     "German + English, conversational, soft",
    "antoine":  "French + English, conversational",
    "jennie":   "Korean + English",
    "kenji":    "Japanese + English",
    "lily":     "Mandarin + English",
    "kevin":    "Korean + English",
    "nova":     "Italian + English",
    "marco":    "Italian + English",
    "sofia":    "Spanish + English",
    "yuki":     "Japanese + English",
    "santiago": "Spanish + English",
    "leo":      "Spanish (Latin American) + English, Colombian",
}
VOICE_LIST = list(VOICE_DESCRIPTIONS.keys())

# Image generation config (grok-imagine-image)
# Aspect ratio options: "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
#   "2:1", "1:2", "19.5:9", "9:19.5", "20:9", "9:20", "auto"
IMAGE_ASPECT_RATIO = "1:1"

# Resolution options: "1k" (standard), "2k" (higher)
IMAGE_SIZE = "1k"

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
