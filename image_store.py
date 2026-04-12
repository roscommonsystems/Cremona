# Image store module for managing generated images
# Stores image data in memory with unique IDs for retrieval and editing

import uuid
import base64
import io
from PIL import Image

# In-memory storage for generated images
# Structure: {image_id: {"data_url": str, "created_at": float, "prompt": str}}
_image_storage: dict = {}

# Maximum number of images to keep per session (to prevent memory bloat)
MAX_STORED_IMAGES = 10


def store_image(data_url: str, prompt: str = "") -> str:
    """
    Store an image data URL and return a unique ID for retrieval.

    Args:
        data_url: The base64 data URL of the image (e.g., "data:image/png;base64,abc123...")
        prompt: The prompt used to generate the image (for context)

    Returns:
        A unique image ID that can be used to retrieve the image later.
    """
    image_id = f"img_{uuid.uuid4().hex[:12]}"

    # Store the image data with metadata
    import time
    _image_storage[image_id] = {
        "data_url": data_url,
        "created_at": time.time(),
        "prompt": prompt,
    }

    # Clean up old images if we exceed the limit
    _cleanup_old_images()

    return image_id


def get_image(image_id: str) -> dict | None:
    """
    Retrieve an image by its ID.

    Args:
        image_id: The unique ID returned by store_image()

    Returns:
        The image data dict with "data_url", "created_at", and "prompt" keys,
        or None if not found.
    """
    return _image_storage.get(image_id)


def get_image_data_url(image_id: str) -> str | None:
    """
    Get just the data URL for an image.

    Args:
        image_id: The unique ID returned by store_image()

    Returns:
        The base64 data URL string, or None if not found.
    """
    image_data = _image_storage.get(image_id)
    if image_data:
        return image_data.get("data_url")
    return None


def get_recent_images(limit: int = 5) -> list[dict]:
    """
    Get the most recently stored images.

    Args:
        limit: Maximum number of images to return

    Returns:
        A list of dicts with "id", "data_url", "created_at", and "prompt" keys.
    """
    # Sort by creation time (most recent first)
    sorted_images = sorted(
        _image_storage.items(),
        key=lambda x: x[1].get("created_at", 0),
        reverse=True
    )

    result = []
    for image_id, data in sorted_images[:limit]:
        result.append({
            "id": image_id,
            "data_url": data["data_url"],
            "created_at": data.get("created_at"),
            "prompt": data.get("prompt", ""),
        })

    return result


def update_image(image_id: str, new_data_url: str, edit_prompt: str = "") -> bool:
    """
    Update an image with new data (for image editing feature).

    Args:
        image_id: The ID of the image to update
        new_data_url: The new image data URL
        edit_prompt: The prompt used to edit the image

    Returns:
        True if the image was found and updated, False otherwise.
    """
    if image_id not in _image_storage:
        return False

    import time
    _image_storage[image_id]["data_url"] = new_data_url
    _image_storage[image_id]["edited_at"] = time.time()
    _image_storage[image_id]["edit_prompt"] = edit_prompt

    return True


def _cleanup_old_images():
    """
    Remove oldest images if we exceed MAX_STORED_IMAGES.
    This prevents memory from growing indefinitely.
    """
    if len(_image_storage) <= MAX_STORED_IMAGES:
        return

    # Sort by creation time and remove oldest
    sorted_ids = sorted(
        _image_storage.items(),
        key=lambda x: x[1].get("created_at", 0)
    )

    # Remove oldest images to get back to limit
    images_to_remove = len(_image_storage) - MAX_STORED_IMAGES
    for i in range(images_to_remove):
        old_id = sorted_ids[i][0]
        del _image_storage[old_id]


def create_thumbnail(data_url: str, max_size: int = 256) -> str:
    """
    Create a smaller thumbnail version of an image.
    Useful for sending to the AI when it needs to reference an image.

    Args:
        data_url: The original base64 data URL
        max_size: Maximum width/height for the thumbnail

    Returns:
        A base64 data URL of the thumbnail image.
    """
    # Extract the base64 data
    header, encoded = data_url.split(",", 1)
    image_data = base64.b64decode(encoded)

    # Open the image
    image = Image.open(io.BytesIO(image_data))

    # Resize maintaining aspect ratio
    image.thumbnail((max_size, max_size))

    # Convert back to base64
    output = io.BytesIO()
    # Use JPEG for smaller size, or PNG if transparency
    if image.mode in ("RGBA", "P"):
        image.save(output, format="PNG")
        new_header = "data:image/png;base64,"
    else:
        image.save(output, format="JPEG", quality=85)
        new_header = "data:image/jpeg;base64,"

    thumbnail_data = base64.b64encode(output.getvalue()).decode("utf-8")

    return new_header + thumbnail_data
