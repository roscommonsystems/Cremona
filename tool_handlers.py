import datetime
import json
import logging
import os

from globals import MEMORIES_FILE_PATH, MAX_MEMORIES


async def get_time(args: dict, ws) -> dict:
    now = datetime.datetime.now()
    return {"time": now.strftime("%I:%M %p"), "date": now.strftime("%A, %B %d")}


async def change_voice(args: dict, ws) -> dict:
    voice = args.get("voice", "")
    await ws.send(json.dumps({"type": "session.update", "session": {"voice": voice}}))
    return {"success": True, "voice": voice}


def load_memories_from_file() -> dict:
    if not os.path.exists(MEMORIES_FILE_PATH):
        return {}
    try:
        with open(memories_file_path, 'r', encoding='utf-8') as f:
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


def build_system_prompt(memory_str: str) -> str:
    base = (
        "You are a voice assistant. Keep responses to 1-2 short sentences. "
        "When you call a tool, always begin your spoken reply with the tool name "
        "(replace underscores with spaces, e.g. 'create memory: Got it, I'll remember that.')."
    )
    if memory_str and memory_str != "No stored memories.":
        return f"{base}\n\n## Remembered about the user:\n{memory_str}"
    return base


async def push_system_prompt(ws) -> None:
    memories = load_memories_from_file()
    prompt = build_system_prompt(format_memories_for_prompt(memories))
    await ws.send(json.dumps({"type": "session.update", "session": {"system_prompt": prompt}}))


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
}


async def execute_tool(event: dict, ws) -> dict:
    handler = HANDLERS.get(event.get("name", ""))
    if handler:
        result = await handler(event.get("args", {}), ws)
    else:
        result = {"error": f"Unknown tool: {event.get('name')}"}
    return {"call_id": event.get("call_id", ""), "result": result}
