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
        "name": "generate_image",
        "description": (
            "Generate an image from a text description using AI. "
            "Call this when the user asks you to create, draw, or generate an image. "
            "The image is saved locally and you will receive the filename."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image to generate."
                }
            },
            "required": ["prompt"],
            "additionalProperties": False
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
    {
        "type": "function",
        "name": "describe_current_image",
        "description": (
            "Provide an extended description of the image currently displayed to the user. "
            "Call this when the user asks you to describe, analyze, or tell them about the current image. "
            "Returns a detailed description of the image content."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "edit_image",
        "description": (
            "Edit the image currently displayed to the user. "
            "Call this when the user asks you to modify, edit, or change the current image. "
            "Send the current image to the Gemini model along with the user's specific edit request. "
            "Returns the edited image which will be displayed to the user."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "edit_request": {
                    "type": "string",
                    "description": "Description of the edit or modification to make to the current image."
                }
            },
            "required": ["edit_request"],
            "additionalProperties": False
        }
    },
]
