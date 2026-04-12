# WebSocket
URL = "wss://agents.assemblyai.com/v1/realtime"

# Audio
SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"

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

# Audio alerts
import pathlib
_ASSETS = pathlib.Path(__file__).parent / "assets"
SOUND_OPEN    = str(_ASSETS / "cremona-open.wav")
SOUND_ERROR   = str(_ASSETS / "cremona-error.wav")
SOUND_WAITING = str(_ASSETS / "cremona-waiting.wav")

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
