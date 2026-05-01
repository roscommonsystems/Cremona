# Image store module for managing the current image
# Stores only ONE image at a time - the most recently generated/edited image

# The current image data - stores the data URL and prompt for the single active image
_current_image: dict | None = None


def store_image(data_url: str, prompt: str = "") -> None:
    """
    Store an image as the current active image.
    Replaces any existing image.

    Args:
        data_url: The base64 data URL of the image (e.g., "data:image/png;base64,abc123...")
        prompt: The prompt used to generate the image (for context)
    """
    global _current_image
    _current_image = {
        "data_url": data_url,
        "prompt": prompt,
    }


def get_current_image() -> dict | None:
    """
    Get the current active image.

    Returns:
        The current image dict with "data_url" and "prompt" keys,
        or None if no image is stored.
    """
    return _current_image


def get_image_data_url() -> str | None:
    """
    Get the data URL for the current image.

    Returns:
        The base64 data URL string, or None if no image is stored.
    """
    if _current_image is None:
        return None
    return _current_image.get("data_url")


def has_image() -> bool:
    """
    Check if there is a current image stored.

    Returns:
        True if an image is stored, False otherwise.
    """
    return _current_image is not None
