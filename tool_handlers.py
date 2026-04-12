import base64
import datetime
import json
import logging
import os
import re
import requests
from datetime import datetime as dt

from config import OPEN_ROUTER_API_KEY
from globals import MEMORIES_FILE_PATH, MAX_MEMORIES, DEFAULT_VOICE, VOICE_DESCRIPTIONS, IMAGE_ASPECT_RATIO, IMAGE_SIZE
from image_store import store_image

current_voice = DEFAULT_VOICE


async def get_time(args: dict, ws) -> dict:
    now = datetime.datetime.now()
    return {"time": now.strftime("%I:%M %p"), "date": now.strftime("%A, %B %d")}


async def change_voice(args: dict, ws) -> dict:
    global current_voice
    voice = args.get("voice", "")
    await ws.send(json.dumps({"type": "session.update", "session": {"voice": voice}}))
    current_voice = voice
    await push_system_prompt(ws)
    return {"success": True, "voice": voice}


def load_memories_from_file() -> dict:
    if not os.path.exists(MEMORIES_FILE_PATH):
        return {}
    try:
        with open(MEMORIES_FILE_PATH, 'r', encoding='utf-8') as f:
            memories_list = json.load(f)
        formatted_memories = {}
        for entry in memories_list:
            if isinstance(entry, dict) and "memory_topic" in entry and "memory_content" in entry:
                formatted_memories[entry["memory_topic"]] = entry["memory_content"]
        return formatted_memories
    except json.JSONDecodeError as e:
        logging.error(f"Memories file is corrupted: {e}")
        return {}
    except Exception as e:
        logging.error(f"Error reading memories file: {e}")
        return {}


def save_memory_to_file(memory_topic: str, memory_content: str) -> bool:
    os.makedirs("data", exist_ok=True)
    try:
        if os.path.exists(MEMORIES_FILE_PATH):
            with open(MEMORIES_FILE_PATH, 'r', encoding='utf-8') as f:
                memories_list = json.load(f)
        else:
            memories_list = []

        topic_found = False
        for entry in memories_list:
            if isinstance(entry, dict) and entry.get("memory_topic") == memory_topic:
                entry["memory_content"] = memory_content
                topic_found = True
                break

        if not topic_found:
            if len(memories_list) >= MAX_MEMORIES:
                memories_list.pop(0)
            memories_list.append({"memory_topic": memory_topic, "memory_content": memory_content})

        with open(MEMORIES_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(memories_list, f, indent=2, ensure_ascii=False)
        return True
    except PermissionError as e:
        logging.error(f"Cannot write to memories file: {e}")
        return False
    except Exception as e:
        logging.error(f"Error saving memory: {e}")
        return False


def format_memories_for_prompt(memories_dict: dict) -> str:
    if not memories_dict:
        return "No stored memories."
    return "\n".join(f"- {topic}: {content}" for topic, content in memories_dict.items())


def build_system_prompt(memory_str: str, voice: str) -> str:
    voice_desc = VOICE_DESCRIPTIONS.get(voice, voice)
    base = (
        "You are a voice assistant. Keep responses to 1-2 short sentences. "
        "When you call a tool, always begin your spoken reply with the tool name "
        "(replace underscores with spaces, e.g. 'create memory: Got it, I'll remember that.'). "
        f"Your current voice is {voice} ({voice_desc})."
    )
    if memory_str and memory_str != "No stored memories.":
        return f"{base}\n\n## Remembered about the user:\n{memory_str}"
    return base


async def push_system_prompt(ws) -> None:
    memories = load_memories_from_file()
    prompt = build_system_prompt(format_memories_for_prompt(memories), current_voice)
    await ws.send(json.dumps({"type": "session.update", "session": {"system_prompt": prompt}}))


async def code_information(args: dict, ws) -> dict:
    file = args.get("file", "")
    allowed = {"main.py", "tools.py", "tool_handlers.py", "globals.py", "config.py", "app.py"}
    if file not in allowed:
        return {"error": f"File '{file}' is not available."}
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, file)
    try:
        with open(path, "r", encoding="utf-8") as f:
            contents = f.read()
        return {"file": file, "contents": contents}
    except Exception as e:
        return {"error": str(e)}


async def generate_image(args: dict, ws) -> dict:
    prompt = args.get("prompt", "")
    if not OPEN_ROUTER_API_KEY:
        return {"error": "OPEN_ROUTER_API_KEY is not configured"}

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "google/gemini-2.5-flash-image",
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image", "text"],
        "image_config": {
            "aspect_ratio": IMAGE_ASPECT_RATIO,
            "image_size": IMAGE_SIZE,
        },
        "stream": False,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        choices = result.get("choices", [])
        if not choices:
            return {"error": "No choices returned from API"}

        message = choices[0].get("message", {})
        images = message.get("images", [])
        if not images:
            return {"error": "No images returned. Model may not have generated an image for this prompt."}

        # Store images in the image store and collect IDs for reference
        image_ids = []
        image_count = 0
        for img in images:
            data_url = img.get("image_url", {}).get("url", "")
            if re.match(r"data:image/(\w+);base64,.+", data_url, re.DOTALL):
                image_id = store_image(data_url, prompt)
                image_ids.append(image_id)
                image_count = image_count + 1
            else:
                logging.warning(f"Unexpected image data format for image")

        if image_count == 0:
            return {"error": "Failed to decode any images"}

        # Return image IDs for retrieval, NOT the full base64 data
        # The full image data is retrieved by app.py and sent to the browser separately
        return {
            "status": "generated",
            "image_ids": image_ids,
            "count": image_count,
            "prompt": prompt,
        }

    except requests.exceptions.Timeout:
        return {"error": "Image generation timed out (60s)"}
    except requests.exceptions.HTTPError as e:
        return {"error": f"API error {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        logging.error(f"generate_image failed: {e}")
        return {"error": str(e)}


async def create_memory(args: dict, ws) -> dict:
    topic = args.get("memory_topic", "")
    content = args.get("memory_content", "")
    success = save_memory_to_file(topic, content)
    if success:
        await push_system_prompt(ws)
        return {"status": "saved", "memory_topic": topic}
    else:
        return {"status": "error", "message": "Failed to save memory"}


HANDLERS = {
    "get_time": get_time,
    "change_voice": change_voice,
    "create_memory": create_memory,
    "code_information": code_information,
    "generate_image": generate_image,
}


async def execute_tool(event: dict, ws) -> dict:
    handler = HANDLERS.get(event.get("name", ""))
    if handler:
        result = await handler(event.get("args", {}), ws)
    else:
        result = {"error": f"Unknown tool: {event.get('name')}"}
    if "error" in result:
        logging.warning(f"[tool error] {event.get('name', 'unknown')}: {result['error']}")
    return {"call_id": event.get("call_id", ""), "result": result}
