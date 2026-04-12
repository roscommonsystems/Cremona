import base64
import datetime
import json
import logging
import os
import re
import requests
import io
from datetime import datetime as dt
from PIL import Image

from config import OPEN_ROUTER_API_KEY
from globals import MEMORIES_FILE_PATH, MAX_MEMORIES, DEFAULT_VOICE, VOICE_DESCRIPTIONS, IMAGE_ASPECT_RATIO, IMAGE_SIZE
from image_store import store_image, get_image_data_url

current_voice = DEFAULT_VOICE


def _sanitize_args_for_display(args: dict) -> dict:
    """Sanitize arguments for terminal display by truncating base64 data."""
    sanitized_args = {}
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 100:
            sanitized_args[key] = value[:50] + "...[truncated]"
        else:
            sanitized_args[key] = value
    return sanitized_args


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


async def describe_current_image(args: dict, ws) -> dict:
    """Describe the image currently displayed to the user using a VLM."""
    # Access the session state from the websocket
    current_image_id = getattr(ws, "current_image_id", None)

    if not current_image_id:
        return {"error": "No image is currently displayed. Please create an image first."}

    # Get the image data URL from the image store
    image_data_url = get_image_data_url(current_image_id)

    if not image_data_url:
        return {"error": "Could not retrieve the current image. It may have expired."}

    if not OPEN_ROUTER_API_KEY:
        return {"error": "OPEN_ROUTER_API_KEY is not configured"}

    # Convert image to JPEG format for better compatibility with Llama 4
    # The Gemini-generated image may be PNG, but many models expect JPEG
    try:
        # Extract base64 data from the data URL
        # Data URL format: data:image/{format};base64,{base64_data}
        if "," not in image_data_url:
            logging.error(f"Invalid data URL format for image {current_image_id}")
            return {"error": "Invalid image data format"}

        header, encoded = image_data_url.split(",", 1)
        image_bytes = base64.b64decode(encoded)

        # Open the image and convert to JPEG
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary (for PNG with transparency)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        # Save as JPEG
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=95)
        jpeg_base64 = base64.b64encode(output.getvalue()).decode("utf-8")

        # Create new data URL with JPEG MIME type
        image_data_url = f"data:image/jpeg;base64,{jpeg_base64}"
        logging.debug(f"Image converted to JPEG format successfully")

    except Exception as e:
        logging.error(f"Failed to convert image to JPEG: {e}")
        return {"error": f"Failed to process image: {str(e)}"}

    logging.debug(f"Attempting to describe image with ID: {current_image_id}")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_API_KEY}",
        "Content-Type": "application/json",
        # Define the HTTP referer to be used for provider tracking
        "HTTP-Referer": "https://www.roscommon.systems/",
        "X-Title": "LimaAI",
    }

    payload = {
        "model": "meta-llama/llama-4-maverick",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please provide a detailed, extended description of this image. Describe the scene, subjects, colors, composition, style, mood, and any notable details."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    }
                ]
            }
        ],
        "stream": False,
    }

    logging.debug(f"Sending request to OpenRouter for image description")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        logging.debug(f"Response received with status: {response.status_code}")
        response.raise_for_status()
        result = response.json()
        logging.debug(f"Response JSON parsed successfully")

        choices = result.get("choices", [])
        if not choices:
            logging.warning("No choices returned from VLM")
            return {"error": "No response from VLM"}

        message = choices[0].get("message", {})
        description = message.get("content", "")

        if not description:
            logging.warning("Empty content received from VLM")
            return {"error": "Empty description received from VLM"}

        logging.info(f"Image description generated successfully")
        return {
            "status": "success",
            "description": description,
            "image_id": current_image_id,
        }

    except requests.exceptions.Timeout:
        logging.error("Image description request timed out")
        return {"error": "Image description timed out (30s)"}
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error from OpenRouter: {e.response.status_code} - {e.response.text[:500]}")
        return {"error": f"API error {e.response.status_code}: {e.response.text[:200]}"}
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse JSON response: {e}")
        return {"error": f"Invalid JSON response from API"}
    except Exception as e:
        logging.error(f"describe_current_image failed: {e}", exc_info=True)
        return {"error": str(e)}


async def edit_image(args: dict, ws) -> dict:
    """Edit the currently displayed image using Gemini's image generation model."""
    edit_request = args.get("edit_request", "")

    if not edit_request:
        return {"error": "No edit request provided."}

    # Access the session state from the websocket
    current_image_id = getattr(ws, "current_image_id", None)

    if not current_image_id:
        return {"error": "No image is currently displayed. Please create an image first."}

    # Get the image data URL from the image store
    image_data_url = get_image_data_url(current_image_id)

    if not image_data_url:
        return {"error": "Could not retrieve the current image. It may have expired."}

    if not OPEN_ROUTER_API_KEY:
        return {"error": "OPEN_ROUTER_API_KEY is not configured"}

    # Convert image to JPEG format for better compatibility with Gemini
    try:
        # Extract base64 data from the data URL
        if "," not in image_data_url:
            logging.error(f"Invalid data URL format for image {current_image_id}")
            return {"error": "Invalid image data format"}

        header, encoded = image_data_url.split(",", 1)
        image_bytes = base64.b64decode(encoded)

        # Open the image and convert to JPEG
        image = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary (for PNG with transparency)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        # Save as JPEG
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=95)
        jpeg_base64 = base64.b64encode(output.getvalue()).decode("utf-8")

        # Create new data URL with JPEG MIME type
        image_data_url = f"data:image/jpeg;base64,{jpeg_base64}"
        logging.debug(f"Image converted to JPEG format successfully")

    except Exception as e:
        logging.error(f"Failed to convert image to JPEG: {e}")
        return {"error": f"Failed to process image: {str(e)}"}

    logging.debug(f"Attempting to edit image with ID: {current_image_id}")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPEN_ROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "google/gemini-2.5-flash-image",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": edit_request
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    }
                ]
            }
        ],
        "modalities": ["image", "text"],
        "image_config": {
            "aspect_ratio": IMAGE_ASPECT_RATIO,
            "image_size": IMAGE_SIZE,
        },
        "stream": False,
    }

    logging.debug(f"Sending request to OpenRouter for image editing")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        logging.debug(f"Response received with status: {response.status_code}")
        response.raise_for_status()
        result = response.json()
        logging.debug(f"Response JSON parsed successfully")

        choices = result.get("choices", [])
        if not choices:
            return {"error": "No choices returned from API"}

        message = choices[0].get("message", {})
        images = message.get("images", [])
        if not images:
            return {"error": "No images returned. Model may not have generated an image for this request."}

        # Store images in the image store and collect IDs for reference
        image_ids = []
        image_count = 0
        for img in images:
            data_url = img.get("image_url", {}).get("url", "")
            if re.match(r"data:image/(\w+);base64,.+", data_url, re.DOTALL):
                image_id = store_image(data_url, edit_request)
                image_ids.append(image_id)
                image_count = image_count + 1
            else:
                logging.warning(f"Unexpected image data format for image")

        if image_count == 0:
            return {"error": "Failed to decode any images"}

        # Return image IDs for retrieval, NOT the full base64 data
        # The full image data is retrieved by app.py and sent to the browser separately
        return {
            "status": "edited",
            "image_ids": image_ids,
            "count": image_count,
            "edit_request": edit_request,
        }

    except requests.exceptions.Timeout:
        logging.error("Image editing request timed out")
        return {"error": "Image editing timed out (60s)"}
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error from OpenRouter: {e.response.status_code} - {e.response.text[:500]}")
        return {"error": f"API error {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        logging.error(f"edit_image failed: {e}", exc_info=True)
        return {"error": str(e)}


HANDLERS = {
    "get_time": get_time,
    "change_voice": change_voice,
    "create_memory": create_memory,
    "code_information": code_information,
    "generate_image": generate_image,
    "describe_current_image": describe_current_image,
    "edit_image": edit_image,
}


async def execute_tool(event: dict, ws) -> dict:
    tool_name = event.get("name", "")
    tool_args = event.get("args", {})

    sanitized_args = _sanitize_args_for_display(tool_args)
    print(f"[Tool Call] name: {tool_name}, args: {sanitized_args}")

    handler = HANDLERS.get(tool_name)
    if handler:
        result = await handler(tool_args, ws)
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    if "error" in result:
        logging.warning(f"[tool error] {tool_name}: {result['error']}")
    return {"call_id": event.get("call_id", ""), "result": result}
