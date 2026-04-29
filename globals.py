# WebSocket
URL = "wss://agents.assemblyai.com/v1/voice"

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
DEFAULT_VOICE = "river"

# Reconnection
MAX_RETRIES = 4
BACKOFF_BASE = 1    # seconds
BACKOFF_CAP = 60    # seconds

# Inactivity
INACTIVITY_TIMEOUT = 15 * 60  # seconds

# Memory
# MEMORIES_FILE_PATH = "data/memories.json"
# MAX_MEMORIES = 10

# Voices
VOICE_DESCRIPTIONS = {
    # English voices — US accent
    "ivy":      "Professional, deliberate, smooth",
    "james":    "Conversational, professional, male",
    "tyler":    "Theatrical, energetic, chatty, jagged",
    "autumn":   "Empathetic, aesthetic, conversational",
    "sam":      "Soft, conversational, young",
    "mia":      "Smooth, conversational, young",
    "bella":    "High-pitched, chatty",
    "david":    "Deep, calming, conversational",
    "jack":     "Smooth, direct, clear, fast-paced",
    "kyle":     "Chatty, nasal, expressive",
    "helen":    "Soft, older, calming",
    "martha":   "Southern, older, warm",
    "river":    "Slow, calming, ASMR",
    "emma":     "Lively, young, conversational",
    "victor":   "Deep, older",
    "eleanor":  "Deeper, older, calming",
    # English voices — British accent
    "sophie":   "British, clear, smooth, instructive, simple",
    "oliver":   "Narrative, British, conversational",
    # Multilingual voices
    "arjun":    "Hindi/Hinglish + English, conversational",
    "ethan":    "Mandarin + English, conversational, native in both",
    "dmitri":   "Russian + English, conversational",
    "lukas":    "German + English, British accent, conversational, smooth",
    "lena":     "German + English, conversational, soft",
    "pierre":   "French + English, conversational",
    "mina":     "Korean + English",
    "ren":      "Japanese + English",
    "mei":      "Mandarin + English",
    "joon":     "Korean + English",
    "giulia":   "Italian + English",
    "luca":     "Italian + English",
    "lucia":    "Spanish + English",
    "hana":     "Japanese + English",
    "mateo":    "Spanish + English",
    "diego":    "Spanish (Latin American) + English, Colombian",
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
