import os
import logging
from pathlib import Path

# Setup logging
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
handlers = [logging.StreamHandler()]

# Try to add file handler, but don't fail if it doesn't work
try:
    import os
    log_dir = '/app/logs'
    log_file = os.path.join(log_dir, 'webhook.log')

    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)

    # Add file handler
    handlers.append(logging.FileHandler(log_file))
except Exception as e:
    # If file logging fails, just continue with console logging
    pass

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=handlers
)
logger = logging.getLogger(__name__)

# Environment Variables
VERSION = os.getenv('VERSION')
TOKEN = os.getenv('TOKEN')
PHONE_NUMBER_ID = os.getenv('PHONE_NUMBER_ID')
YOUR_VERIFY_TOKEN = os.getenv('YOUR_VERIFY_TOKEN')
Z_TRANSACT_ACCESS_TOKEN = os.getenv('Z_TRANSACT_ACCESS_TOKEN')
Z_TRANSACT_API_URL = os.getenv('Z_TRANSACT_API_URL')

# Config
CONFIG = {
    "VERIFY_TOKEN": YOUR_VERIFY_TOKEN,
    "ACCESS_TOKEN": TOKEN,
    "PHONE_NUMBER_ID": PHONE_NUMBER_ID,
    "APP_SECRET": os.getenv("WHATSAPP_APP_SECRET"),
    "WEBHOOK_URL": os.getenv("WEBHOOK_URL", "/webhook"),
    "MEDIA_STORAGE_PATH": os.getenv("MEDIA_STORAGE_PATH", "/app/media"),
    "Z_TRANSACT_ACCESS_TOKEN": Z_TRANSACT_ACCESS_TOKEN,
    "Z_TRANSACT_API_URL": Z_TRANSACT_API_URL
}

# File Type Detection and Extension Mapping
MIME_TYPE_MAP = {
    # PDF
    "application/pdf": "pdf",

    # Microsoft Office Documents
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",

    # CSV and Text
    "text/csv": "csv",
    "text/plain": "txt",
    "text/html": "html",
    "text/xml": "xml",

    # Images
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",

    # Audio
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/ogg": "ogg",
    "audio/m4a": "m4a",
    "audio/amr": "amr",

    # Video
    "video/mp4": "mp4",
    "video/3gpp": "3gp",
    "video/quicktime": "mov",
    "video/webm": "webm",

    # Archives
    "application/zip": "zip",
    "application/x-rar-compressed": "rar",
    "application/x-7z-compressed": "7z",
    "application/x-tar": "tar",
    "application/gzip": "gz",

    # Other
    "application/octet-stream": "bin"
}

# Create media storage directory
def ensure_media_directory():
    """Create media directory structure if it doesn't exist"""
    media_base = Path(CONFIG["MEDIA_STORAGE_PATH"])
    for subdir in ["documents", "images", "audio", "video", "other"]:
        (media_base / subdir).mkdir(parents=True, exist_ok=True)

    # Create logs directory
    Path("/app/logs").mkdir(parents=True, exist_ok=True)