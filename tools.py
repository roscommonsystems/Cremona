from globals import VOICE_LIST, VOICE_DESCRIPTIONS

# Build voice descriptions string using explicit loop for readability
_voice_description_parts = []
for voice in VOICE_LIST:
    description = VOICE_DESCRIPTIONS[voice]
    formatted_voice = f"{voice} ({description})"
    _voice_description_parts.append(formatted_voice)
_voice_desc_str = ", ".join(_voice_description_parts)

TOOLS = [
    # {
    #     "type": "function",
    #     "name": "create_memory",
    #     "description": (
    #         "Save a piece of information to persistent memory. "
    #         "Use this when the user expresses a preference or asks you to remember something "
    #         "(e.g. 'remember I prefer concise answers', 'I work in finance'). "
    #         "Memories are loaded on startup and injected into your system prompt."
    #     ),
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "memory_topic": {
    #                 "type": "string",
    #                 "description": "Short category label for the memory (e.g. 'communication style')."
    #             },
    #             "memory_content": {
    #                 "type": "string",
    #                 "description": "The actual information to remember (e.g. 'user prefers concise responses')."
    #             }
    #         },
    #         "required": ["memory_topic", "memory_content"]
    #     }
    # },
    # {
    #     "type": "function",
    #     "name": "change_voice",
    #     "description": (
    #         f"Change the agent's voice. Call this when the user asks to change, switch, or use a different voice. "
    #         f"Pick the voice that best matches the user's request based on these descriptions: {_voice_desc_str}."
    #     ),
    #     "parameters": {
    #         "type": "object",
    #         "properties": {
    #             "voice": {
    #                 "type": "string",
    #                 "description": "The voice name to switch to.",
    #                 "enum": VOICE_LIST
    #             }
    #         },
    #         "required": ["voice"]
    #     }
    # },
    {
        "type": "function",
        "name": "generate_image",
        "description": (
            "Generate an image from a text description using AI. "
            "Call this when the user asks you to create, draw, or generate an image. "
            "The image is saved locally and you will receive the filename."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image to generate."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "type": "function",
        "name": "code_information",
        "description": (
            "Read the source code of a file that makes up this AI agent. "
            "Use this to accurately describe how components work or interact. "
            "Available files: app.py (session/WebSocket logic), tools.py (tool schemas), "
            "tool_handlers.py (tool implementations), globals.py (constants/config), config.py (env vars)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "The source file to read.",
                    "enum": ["app.py", "tools.py", "tool_handlers.py", "globals.py", "config.py"]
                }
            },
            "required": ["file"]
        }
    },
    {
        "type": "function",
        "name": "describe_current_image",
        "description": (
            "Provide an extended description of the image currently displayed to the user. "
            "Call this when the user asks you to describe, analyze, or tell them about the current image. "
            "DO NOT call this when the user wants to modify, edit, zoom, pan, crop, or change the image in any way - "
            "use edit_image instead for those requests. "
            "Returns a detailed description of the image content. "
            "If the user asks about a specific area or aspect (e.g. 'left side', 'the person', 'the building'), "
            "provide that as the focus parameter."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focus": {
                    "type": "string",
                    "description": "Optional specific area or aspect to focus on (e.g. 'left side', 'the person', 'the background'). If not provided, describe the entire image."
                }
            },
            "required": []
        }
    },
    {
        "type": "function",
        "name": "download_image",
        "description": (
            "Download the image currently displayed to the user. "
            "Call this when the user asks to save or download the current image. "
            "Only works when an image is visible on screen."
        ),
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "type": "function",
        "name": "edit_image",
        "description": (
            "Edit the image currently displayed to the user. "
            "Call this when the user asks you to modify, edit, update, or change the current image. "
            "Also call this when the user asks for zoom in/out, pan left/right/up/down, or crop operations. "
            "Send the current image to Grok Imagine along with the user's specific edit request. "
            "Returns the edited image which will be displayed to the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "edit_request": {
                    "type": "string",
                    "description": "Description of the edit or modification to make to the current image."
                }
            },
            "required": ["edit_request"]
        }
    },
]
