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

# Voices
VOICE_LIST = [
    "alexei", "alexis", "andy", "anna", "antoine", "audrey", "brian", "claire",
    "dawn", "diana", "dylan", "gautam", "grace", "jennie", "josh", "kai", "kenji",
    "kevin", "leo", "lily"
]
