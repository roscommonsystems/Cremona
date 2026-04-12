from globals import VOICE_LIST, VOICE_DESCRIPTIONS

_voice_desc_str = ", ".join(f"{v} ({VOICE_DESCRIPTIONS[v]})" for v in VOICE_LIST)

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
            f"Pick the voice that best matches the user's request based on these descriptions: {_voice_desc_str}."
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
    {
        "type": "function",
        "name": "code_information",
        "description": (
            "Read the source code of a file that makes up this AI agent. "
            "Use this to accurately describe how components work or interact. "
            "Available files: main.py (session/WebSocket logic), tools.py (tool schemas), "
            "tool_handlers.py (tool implementations), globals.py (constants/config), env.py (env vars)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "The source file to read.",
                    "enum": ["main.py", "tools.py", "tool_handlers.py", "globals.py", "env.py"]
                }
            },
            "required": ["file"],
            "additionalProperties": False
        }
    },
]
