from globals import VOICE_LIST

TOOLS = [
    {
        "type": "function",
        "name": "get_time",
        "description": "Get the current time and date.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "type": "function",
        "name": "create_memory",
        "description": (
            "Save a piece of information to persistent memory. "
            "Use this when the user expresses a preference or asks you to remember something "
            "(e.g. 'remember I prefer concise answers', 'I work in finance'). "
            "Memories are loaded on startup and injected into your system prompt."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "memory_topic": {
                    "type": "string",
                    "description": "Short category label for the memory (e.g. 'communication style')."
                },
                "memory_content": {
                    "type": "string",
                    "description": "The actual information to remember (e.g. 'user prefers concise responses')."
                }
            },
            "required": ["memory_topic", "memory_content"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "change_voice",
        "description": (
            "Change the agent's voice. Call this when the user asks to change, switch, or use a different voice. "
            "Pick the voice that best matches the user's request based on these descriptions: "
            "alexei (Russian male), alexis (American girl), andy (stoned college kid male), "
            "anna (pleasant American female, hippy), antoine (French young male), "
            "audrey (mature neutral accent female, dramatic), brian (young American boy), "
            "claire (American girl, upbeat and friendly), dawn (soft-voiced American female), "
            "diana (refined mature elegant female), dylan (straightforward middle-aged American male), "
            "gautam (Indian male, slow-paced), grace (mysterious dramatic mature woman), "
            "jennie (dainty delicate young female), josh (neutral middle-aged American male), "
            "kai (ditzy California female), kenji (confident male with Japanese accent), "
            "kevin (clear casual neutral conversational male), leo (deep male with Italian/Portuguese accent), "
            "lily (cultured academic female)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "voice": {
                    "type": "string",
                    "description": "The voice name to switch to.",
                    "enum": VOICE_LIST
                }
            },
            "required": ["voice"]
        }
    },
]
