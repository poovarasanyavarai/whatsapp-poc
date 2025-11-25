import uuid
import time
from pathlib import Path
from src.config import CONFIG, MIME_EXTENSIONS

# File size limits (bytes)
SIZE_LIMITS = {
    "image": 5 * 1024 * 1024,
    "video": 100 * 1024 * 1024,
    "audio": 16 * 1024 * 1024,
    "document": 100 * 1024 * 1024,
    "sticker": 1024 * 1024
}

def get_file_extension(mime_type: str, filename: str = None) -> str:
    """Get file extension from MIME type or filename"""
    if mime_type in MIME_EXTENSIONS:
        return MIME_EXTENSIONS[mime_type]

    if filename and '.' in filename:
        return filename.split('.')[-1].lower()

    return "bin"

def get_media_subdirectory(msg_type: str, mime_type: str = None) -> str:
    """Get storage subdirectory for media type"""
    if msg_type in ["image", "video"]:
        return msg_type + "s"
    elif msg_type == "audio":
        return "audio"
    elif msg_type == "document":
        if mime_type and mime_type.startswith("image/"):
            return "images"
        elif mime_type and mime_type.startswith("video/"):
            return "video"
        elif mime_type and mime_type.startswith("audio/"):
            return "audio"
        return "documents"
    return "other"

def generate_safe_filename(phone: str, msg_type: str, mime_type: str, original_filename: str = None) -> str:
    """Generate safe filename"""
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8]
    phone_clean = phone.replace("+", "").replace(" ", "")
    extension = get_file_extension(mime_type, original_filename)

    if original_filename and original_filename.strip():
        safe_name = "".join(c for c in original_filename if c.isalnum() or c in "._-")[:50]
        return f"{phone_clean}_{msg_type}_{timestamp}_{safe_name}.{extension}"

    return f"{phone_clean}_{msg_type}_{timestamp}_{unique_id}.{extension}"

def validate_file_size(file_size: int, msg_type: str) -> bool:
    """Check if file size is within limits"""
    limit = SIZE_LIMITS.get(msg_type, 100 * 1024 * 1024)
    return file_size <= limit