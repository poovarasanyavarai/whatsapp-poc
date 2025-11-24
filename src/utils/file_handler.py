import uuid
from datetime import datetime
from pathlib import Path
from src.config import CONFIG, MIME_TYPE_MAP, logger

def get_file_extension(mime_type: str, filename: str = None) -> str:
    """Get appropriate file extension based on MIME type and filename"""
    # First try MIME type mapping
    if mime_type in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[mime_type]

    # Fallback to filename extension if available
    if filename and "." in filename:
        return filename.split(".")[-1].lower()

    # Default to generic extension
    return "bin"

def get_media_subdirectory(msg_type: str, mime_type: str) -> str:
    """Determine which subdirectory to store media in"""
    if msg_type in ["image", "video"]:
        return msg_type + "s"
    elif msg_type == "audio":
        return "audio"
    elif msg_type == "document":
        if mime_type.startswith("image/"):
            return "images"
        elif mime_type.startswith("video/"):
            return "video"
        elif mime_type.startswith("audio/"):
            return "audio"
        else:
            return "documents"
    else:
        return "other"

def generate_safe_filename(phone: str, msg_type: str, mime_type: str, original_filename: str = None) -> str:
    """Generate a safe filename with proper extension"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    phone_clean = phone.replace("+", "").replace(" ", "")

    # Get appropriate extension
    extension = get_file_extension(mime_type, original_filename)

    # Create filename: phone_type_timestamp_uuid.extension
    if original_filename and original_filename.strip():
        # Use original filename but make it safe
        safe_name = "".join(c for c in original_filename if c.isalnum() or c in "._-")[:50]
        return f"{phone_clean}_{msg_type}_{timestamp}_{safe_name}.{extension}"
    else:
        return f"{phone_clean}_{msg_type}_{timestamp}_{unique_id}.{extension}"

def validate_file_size(file_size: int, msg_type: str) -> bool:
    """Validate file size limits (in bytes)"""
    size_limits = {
        "image": 5 * 1024 * 1024,      # 5MB
        "video": 100 * 1024 * 1024,    # 100MB
        "audio": 16 * 1024 * 1024,     # 16MB
        "document": 100 * 1024 * 1024, # 100MB
        "sticker": 1 * 1024 * 1024,    # 1MB
    }

    limit = size_limits.get(msg_type, 100 * 1024 * 1024)  # Default 100MB
    return file_size <= limit