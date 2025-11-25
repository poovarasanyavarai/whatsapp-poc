import os
import logging
from pathlib import Path

# Simple logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Environment variable helper
def env_or_none(key: str) -> str | None:
    """Get environment variable or None"""
    return os.getenv(key)

# Load configuration from environment
CONFIG = {
    "VERIFY_TOKEN": env_or_none('YOUR_VERIFY_TOKEN'),
    "ACCESS_TOKEN": env_or_none('TOKEN'),
    "PHONE_NUMBER_ID": env_or_none('PHONE_NUMBER_ID'),
    "APP_SECRET": env_or_none("WHATSAPP_APP_SECRET"),
    "WEBHOOK_URL": env_or_none("WEBHOOK_URL") or "/webhook",
    "MEDIA_STORAGE_PATH": env_or_none("MEDIA_STORAGE_PATH") or "/app/media",
    "Z_TRANSACT_ACCESS_TOKEN": env_or_none('Z_TRANSACT_ACCESS_TOKEN'),
    "Z_TRANSACT_API_URL": env_or_none('Z_TRANSACT_API_URL'),
    "ZAGENT_API_URL": env_or_none('ZAGENT_API_URL'),
    "ZAGENT_ACCESS_TOKEN": env_or_none('ZAGENT_ACCESS_TOKEN'),
    "ZAGENT_BOT_UUID": env_or_none('ZAGENT_BOT_UUID'),
    "ZAGENT_CONVERSATION_ID": env_or_none('ZAGENT_CONVERSATION_ID')
}

# MIME type extensions
MIME_EXTENSIONS = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/csv": "csv",
    "text/plain": "txt",
    "text/html": "html",
    "text/xml": "xml",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/ogg": "ogg",
    "audio/m4a": "m4a",
    "audio/amr": "amr",
    "video/mp4": "mp4",
    "video/3gpp": "3gp",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "application/zip": "zip",
    "application/x-rar-compressed": "rar",
    "application/x-7z-compressed": "7z",
    "application/x-tar": "tar",
    "application/gzip": "gz",
    "application/octet-stream": "bin"
}

def setup_directories():
    """Create required directories"""
    base_path = Path(CONFIG["MEDIA_STORAGE_PATH"])
    for subdir in ["documents", "images", "audio", "video", "other"]:
        (base_path / subdir).mkdir(parents=True, exist_ok=True)
    Path("/app/logs").mkdir(parents=True, exist_ok=True)