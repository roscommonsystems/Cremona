import asyncio
import base64
import datetime
import json
import logging
import os
import re
import requests
import time
import io
from PIL import Image
from openai import AsyncOpenAI

from config import OPEN_ROUTER_API_KEY
from globals import MEMORIES_FILE_PATH, MAX_MEMORIES, DEFAULT_VOICE, VOICE_DESCRIPTIONS, IMAGE_ASPECT_RATIO, IMAGE_SIZE
from image_store import store_image, get_image_data_url

# Create the OpenAI client configured for OpenRouter
openai_client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPEN_ROUTER_API_KEY,
)

current_voice = DEFAULT_VOICE


def _sanitize_args_for_display(args: dict) -> dict:
    """Sanitize arguments for terminal display by truncating base64 data."""
    sanitized_args = {}
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 250:
            sanitized_args[key] = value[:250] + "...[truncated]"
        else:
            sanitized_args[key] = value
    return sanitized_args


def _convert_image_to_jpeg(image_data_url: str) -> tuple[str | None, str | None]:
    """
    Convert an image data URL to JPEG format.

    Args:
        image_data_url: The source data URL (e.g., "data:image/png;base64,...")

    Returns:
        A tuple of (jpeg_data_url, error_message).
        On success, jpeg_data_url is the converted data URL and error_message is None.
        On failure, jpeg_data_url is None and error_message contains the reason.
    """
    if "," not in image_data_url:
        logging.error("Invalid data URL format for current image")
        return None, "Invalid image data format"

    try:
        _, encoded = image_data_url.split(",", 1)
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
        jpeg_data_url = f"data:image/jpeg;base64,{jpeg_base64}"
        logging.debug("Image converted to JPEG format successfully")
        return jpeg_data_url, None

    except Exception as e:
        logging.error(f"Failed to convert image to JPEG: {e}")
        return None, f"Failed to process image: {str(e)}"


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
        print(f"[generate_image] Sending request to OpenRouter ({IMAGE_SIZE}, {IMAGE_ASPECT_RATIO})...")
        _t0 = time.perf_counter()
        response = await asyncio.to_thread(
            requests.post, url, headers=headers, json=payload, timeout=45
        )
        _elapsed = time.perf_counter() - _t0
        print(f"[generate_image] Response received in {_elapsed:.2f}s — status {response.status_code}")
        response.raise_for_status()
        result = response.json()

        choices = result.get("choices", [])
        if not choices:
            logging.warning(f"generate_image: no choices. Full response: {json.dumps(result)[:500]}")
            return {"error": "No choices returned from API"}

        message = choices[0].get("message", {})
        images = message.get("images", [])
        if not images:
            return {"error": "No images returned. Model may not have generated an image for this prompt."}

        # Store the first valid image as the current image
        for img in images:
            data_url = img.get("image_url", {}).get("url", "")
            if re.match(r"data:image/(\w+);base64,.+", data_url, re.DOTALL):
                store_image(data_url, prompt)
                return {
                    "status": "generated",
                    "has_image": True,
                    "prompt": prompt,
                }

        return {"error": "Failed to decode image"}

    except requests.exceptions.Timeout:
        return {"error": "Image generation timed out (45s)"}
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
    # Get the optional focus parameter from the user's request
    focus = args.get("focus", "")

    # Get the current image data URL
    image_data_url = get_image_data_url()
    if not image_data_url:
        return {"error": "No image is currently displayed. Please create an image first."}

    if not OPEN_ROUTER_API_KEY:
        return {"error": "OPEN_ROUTER_API_KEY is not configured"}

    # Convert image to JPEG format for better compatibility with Llama 4
    # The Gemini-generated image may be PNG, but many models expect JPEG
    image_data_url, error_message = _convert_image_to_jpeg(image_data_url)
    if error_message:
        return {"error": error_message}

    logging.debug("Attempting to describe current image")

    # Build the prompt based on whether a specific focus was requested
    if focus:
        description_prompt = f"The user is asking specifically about: {focus}. Please focus your description on this aspect. If applicable, describe this area or subject in detail, including relevant context from the rest of the image."
    else:
        description_prompt = "Please provide a detailed, extended description of this image. Describe the scene, subjects, colors, composition, style, mood, and any notable details."

    try:
        response = await openai_client.chat.completions.create(
            model="meta-llama/llama-4-maverick",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": description_prompt
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
            extra_headers={
                "HTTP-Referer": "https://www.roscommon.systems/",
                "X-Title": "LimaAI",
            },
            timeout=30,
        )

        logging.debug("Response received from OpenRouter")

        description = response.choices[0].message.content

        if not description:
            logging.warning("Empty content received from VLM")
            return {"error": "Empty description received from VLM"}

        logging.info("Image description generated successfully")
        return {
            "status": "success",
            "description": description,
        }

    except Exception as e:
        logging.error(f"describe_current_image failed: {e}", exc_info=True)
        return {"error": str(e)}


async def edit_image(args: dict, ws) -> dict:
    """Edit the currently displayed image using Gemini's image generation model."""
    edit_request = args.get("edit_request", "")

    if not edit_request:
        return {"error": "No edit request provided."}

    # Get the current image data URL
    image_data_url = get_image_data_url()
    if not image_data_url:
        return {"error": "No image is currently displayed. Please create an image first."}

    if not OPEN_ROUTER_API_KEY:
        return {"error": "OPEN_ROUTER_API_KEY is not configured"}

    # Convert image to JPEG format for better compatibility with Gemini
    image_data_url, error_message = _convert_image_to_jpeg(image_data_url)
    if error_message:
        return {"error": error_message}

    logging.debug("Attempting to edit current image")

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

    logging.debug("Sending request to OpenRouter for image editing")

    try:
        response = await asyncio.to_thread(
            requests.post, url, headers=headers, json=payload, timeout=45
        )
        logging.debug(f"Response received with status: {response.status_code}")
        response.raise_for_status()
        result = response.json()
        logging.debug("Response JSON parsed successfully")

        choices = result.get("choices", [])
        if not choices:
            logging.warning(f"edit_image: no choices. Full response: {json.dumps(result)[:500]}")
            return {"error": "No choices returned from API"}

        message = choices[0].get("message", {})
        images = message.get("images", [])
        if not images:
            logging.warning(f"edit_image: no images in choices. Full response: {json.dumps(result)[:500]}")
            return {"error": "No images returned. Model may not have generated an image for this request."}

        # Store the first valid image as the current image
        for img in images:
            data_url = img.get("image_url", {}).get("url", "")
            if re.match(r"data:image/(\w+);base64,.+", data_url, re.DOTALL):
                store_image(data_url, edit_request)
                return {
                    "status": "edited",
                    "has_image": True,
                    "edit_request": edit_request,
                }

        return {"error": "Failed to decode image"}

    except requests.exceptions.Timeout:
        logging.error("Image editing request timed out")
        return {"error": "Image editing timed out (45s)"}
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error from OpenRouter: {e.response.status_code} - {e.response.text[:5000]}")
        return {"error": f"API error {e.response.status_code}: {e.response.text[:2000]}"}
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
    t0 = time.perf_counter()
    if handler:
        result = await handler(tool_args, ws)
    else:
        result = {"error": f"Unknown tool: {tool_name}"}
    elapsed = time.perf_counter() - t0

    if "error" in result:
        logging.warning(f"[tool error] {tool_name} (took {elapsed:.2f}s): {json.dumps(result)}")
    else:
        print(f"[Tool Done] {tool_name} completed in {elapsed:.2f}s")
    return {"call_id": event.get("call_id", ""), "result": result}


if __name__ == "__main__":
    # Test the describe_current_image function by loading the logo image
    # and attempting to describe it using the VLM.
    import asyncio

    LOGO_PATH = "assets/circular_logo_teal.png"

    async def run_test():
        # Load the logo image and convert to data URL format
        if not os.path.exists(LOGO_PATH):
            print(f"Error: Logo file not found at {LOGO_PATH}")
            return

        try:
            with open(LOGO_PATH, "rb") as f:
                image_bytes = f.read()

            # Convert to base64 encoded data URL
            base64_image = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:image/png;base64,{base64_image}"

            # Store the image so describe_current_image can retrieve it
            store_image(data_url, "circular_logo_teal.png")
            print(f"Stored image from {LOGO_PATH}")

        except Exception as e:
            print(f"Error loading/storing image: {e}")
            return

        # Create a mock WebSocket object that does nothing
        # The describe_current_image function expects a ws argument with a send method
        class MockWebSocket:
            async def send(self, message):
                # Just ignore any websocket messages during testing
                pass

        mock_ws = MockWebSocket()

        # Call describe_current_image with empty args (no focus)
        print("\nCalling describe_current_image...")
        result = await describe_current_image({}, mock_ws)

        # Print the result
        print("\n--- Result ---")
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Status: {result.get('status', 'unknown')}")
            print(f"Description: {result.get('description', 'No description returned')}")

    # Run the async test
    asyncio.run(run_test())
