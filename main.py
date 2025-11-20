from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
import os
import hashlib
import hmac
import httpx
import json
import logging
from datetime import datetime
from pathlib import Path
import uuid

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/app/logs/webhook.log')
    ]
)
logger = logging.getLogger(__name__)
app = FastAPI(title="WhatsApp Webhook API", version="1.0.0")

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

# Z-Transact API Functions
async def upload_to_z_transact(file_content: bytes, filename: str, mime_type: str) -> dict | None:
    """Upload file to Z-Transact API"""
    if not CONFIG["Z_TRANSACT_ACCESS_TOKEN"] or not CONFIG["Z_TRANSACT_API_URL"]:
        logger.error("Z-Transact API configuration missing")
        return None

    try:
        # Use cookies for authentication like the original API call
        headers = {
            "accept": "application/json"
        }
        cookies = {
            "access_token": CONFIG["Z_TRANSACT_ACCESS_TOKEN"]
        }

        async with httpx.AsyncClient(timeout=60.0, headers=headers, cookies=cookies) as client:
            url = f"{CONFIG['Z_TRANSACT_API_URL']}/documents"

            # Prepare multipart form data
            files = {
                "file": (filename, file_content, mime_type)
            }

            logger.info(f"Uploading to Z-Transact: {filename} ({len(file_content)} bytes)")

            response = await client.post(url, files=files)

            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                logger.info(f"Successfully uploaded to Z-Transact: {result}")
                return result
            else:
                logger.error(f"Z-Transact upload failed: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        logger.error(f"Z-Transact upload error: {e}")
        return None

# Models
class WebhookData(BaseModel):
    object: str
    entry: list[dict]

# Utils
def verify_signature(body: bytes, signature: str) -> bool:
    """Verify webhook signature"""
    if not CONFIG["APP_SECRET"]:
        return False

    expected = hmac.new(
        CONFIG["APP_SECRET"].encode(),
        body,
        hashlib.sha256
    ).hexdigest()

    return signature == f"sha256={expected}"

async def download_media(media_id: str) -> dict | None:
    """Download media from WhatsApp - returns dict with file data and metadata"""
    logger.info(f"Downloading media: {media_id}")

    if not CONFIG["ACCESS_TOKEN"]:
        logger.error("No access token configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get media URL
            meta_url = f"https://graph.facebook.com/v18.0/{media_id}"
            resp = await client.get(
                meta_url,
                headers={"Authorization": f"Bearer {CONFIG['ACCESS_TOKEN']}"}
            )

            if resp.status_code != 200:
                logger.error(f"Failed to get media metadata: {resp.status_code}")
                return None

            media_data = resp.json()
            media_url = media_data.get("url")
            mime_type = media_data.get("mime_type", "unknown")
            file_size = media_data.get("file_size", 0)
            filename = media_data.get("filename", None)

            logger.info(f"Media metadata: URL={media_url[:50] if media_url else 'None'}..., MIME={mime_type}, Size={file_size}")

            if not media_url:
                logger.error("No media URL in response")
                return None

            # Download file
            logger.info(f"Downloading media file...")
            file_resp = await client.get(
                media_url,
                headers={"Authorization": f"Bearer {CONFIG['ACCESS_TOKEN']}"}
            )

            if file_resp.status_code == 200:
                file_content = file_resp.content
                logger.info(f"Media downloaded successfully: {len(file_content)} bytes")

                return {
                    "content": file_content,
                    "mime_type": mime_type,
                    "file_size": len(file_content),
                    "filename": filename,
                    "download_url": media_url
                }
            else:
                logger.error(f"File download failed: {file_resp.status_code}")
                return None

    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

async def process_message(data: dict):
    """Process incoming message"""
    logger.info(f"Processing message: {list(data.keys())}")

    if "messages" not in data:
        logger.warning("No messages in data")
        return

    messages = data["messages"]
    msg = messages[0]
    msg_id = msg.get("id", "unknown")
    msg_type = msg.get("type", "text")
    from_number = msg.get("from", "unknown")
    timestamp = msg.get("timestamp", "unknown")

    logger.info(f"Message: {msg_type} from {from_number}")

    # Extract customer info
    customer = {}
    if "contacts" in data:
        contact = data["contacts"][0]
        customer = {
            "wa_id": contact.get("wa_id", "unknown"),
            "name": contact.get("profile", {}).get("name", "Unknown")
        }
        logger.info(f"Customer: {customer['name']} ({customer['wa_id']})")

    # Extract content based on type
    content = ""
    downloaded_media = None
    media_id = None
    media_details = {}

    if msg_type in ["image", "video"]:
        media_data = msg[msg_type]
        content = media_data.get("caption", "")
        media_id = media_data["id"]

        media_details = {
            "id": media_id,
            "caption": content,
            "mime_type": media_data.get("mime_type", "unknown"),
            "sha256": media_data.get("sha256", "unknown"),
            "file_size": media_data.get("file_size", 0)
        }

        logger.info(f"Media: ID={media_id}, MIME={media_details['mime_type']}, Size={media_details['file_size']}")
        downloaded_media = await download_media(media_id)

    elif msg_type == "text":
        content = msg["text"]["body"]
        logger.info(f"Text: {content[:50]}...")

    elif msg_type in ["audio", "document", "sticker"]:
        media_data = msg[msg_type]
        media_id = media_data["id"]
        file_name = media_data.get("filename", f"{msg_type}_{media_id}")
        mime_type = media_data.get("mime_type", "unknown")
        sha256 = media_data.get("sha256", "unknown")
        file_size = media_data.get("file_size", 0)

        logger.info(f"{msg_type}: {file_name} ({file_size} bytes)")

        metadata_url = f"https://graph.facebook.com/v18.0/{media_id}"
        logger.info(f"Metadata URL: {metadata_url}")

        downloaded_media = await download_media(media_id)

        if downloaded_media:
            logger.info(f"{msg_type} downloaded successfully")
        else:
            logger.warning(f"{msg_type} download failed")

    else:
        logger.warning(f"Unknown message type: {msg_type}")

    # Store message
    try:
        await store_message(from_number, customer, msg_type, content, downloaded_media)
        logger.info("Message processed successfully")
    except Exception as e:
        logger.error(f"Message storage failed: {e}")
        raise

async def store_message(phone: str, customer: dict, msg_type: str, content: str, media_data: dict = None):
    """Store message with file saving capabilities"""
    try:
        # Ensure media directories exist
        ensure_media_directory()

        # Prepare message data
        message_data = {
            "phone": phone,
            "customer": customer,
            "type": msg_type,
            "content": content,
            "has_media": media_data is not None,
            "timestamp": datetime.now(),
            "media_file_path": None,
            "media_metadata": None
        }

        if media_data:
            # Validate file size
            if not validate_file_size(media_data["file_size"], msg_type):
                logger.warning(f"File too large: {media_data['file_size']} bytes")
                message_data["has_media"] = False
                message_data["media_error"] = "File size exceeds limit"
            else:
                # Determine subdirectory and generate filename
                subdirectory = get_media_subdirectory(msg_type, media_data["mime_type"])
                filename = generate_safe_filename(
                    phone, msg_type, media_data["mime_type"], media_data.get("filename")
                )

                # Create full file path
                media_base = Path(CONFIG["MEDIA_STORAGE_PATH"])
                file_path = media_base / subdirectory / filename

                # Save file to disk
                try:
                    with open(file_path, "wb") as f:
                        f.write(media_data["content"])

                    logger.info(f"File saved: {file_path}")

                    # Update message data with file info
                    message_data["media_file_path"] = str(file_path)
                    message_data["media_metadata"] = {
                        "original_filename": media_data.get("filename"),
                        "saved_filename": filename,
                        "mime_type": media_data["mime_type"],
                        "file_size": media_data["file_size"],
                        "subdirectory": subdirectory,
                        "download_url": media_data.get("download_url"),
                        "extension": get_file_extension(media_data["mime_type"], media_data.get("filename"))
                    }

                    # Upload document to Z-Transact if it's a business document type
                    if media_data["mime_type"] in [
                        "application/pdf",
                        "application/msword",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "application/vnd.ms-excel",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "text/csv",
                        "text/plain",
                        "application/zip",
                        "application/vnd.ms-powerpoint",
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    ]:
                        logger.info(f"Business document detected: {media_data['mime_type']} -> uploading to Z-Transact")

                        # Get original filename or use saved filename
                        upload_filename = media_data.get("filename", filename)
                        if not upload_filename or upload_filename == f"{msg_type}_{media_id}":
                            upload_filename = filename

                        # Upload to Z-Transact
                        z_transact_result = await upload_to_z_transact(
                            media_data["content"],
                            upload_filename,
                            media_data["mime_type"]
                        )

                        if z_transact_result:
                            logger.info(f"Document uploaded to Z-Transact successfully")
                            message_data["z_transact_upload"] = {
                                "status": "success",
                                "upload_result": z_transact_result,
                                "upload_filename": upload_filename
                            }
                        else:
                            logger.error(f"Failed to upload document to Z-Transact")
                            message_data["z_transact_upload"] = {
                                "status": "failed",
                                "error": "Upload failed"
                            }

                except Exception as save_error:
                    logger.error(f"File save error: {save_error}")
                    message_data["media_error"] = f"Save failed: {save_error}"
                    message_data["has_media"] = False

        logger.info(f"Message data ready for storage")

    except Exception as e:
        logger.error(f"Storage error: {e}")
        raise

# Routes
@app.get(CONFIG["WEBHOOK_URL"])
async def verify_webhook(request: Request):
    """Verify webhook endpoint"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    logger.info(f"Webhook verification from {client_ip}: mode={mode}, token={token}")

    if mode == "subscribe" and token == CONFIG["VERIFY_TOKEN"]:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(challenge)

    logger.warning("Webhook verification failed")
    raise HTTPException(status_code=403, detail="Invalid verification")

@app.post(CONFIG["WEBHOOK_URL"])
async def handle_webhook(request: Request):
    """Handle webhook messages"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    signature = request.headers.get("x-hub-signature-256")
    content_type = request.headers.get("content-type", "unknown")

    body = await request.body()

    logger.info(f"Webhook received from {client_ip}: {len(body)} bytes")

    # Skip signature verification for POST requests
    try:
        data = json.loads(body)

        if data.get("object") == "whatsapp_business_account":
            logger.info("WhatsApp business account webhook")

            for entry in data.get("entry", []):
                logger.info(f"Processing entry: {entry.get('id', 'unknown')}")

                for change in entry.get("changes", []):
                    field = change.get("field", "unknown")
                    logger.info(f"Processing change: {field}")

                    if field == "messages":
                        await process_message(change.get("value", {}))
                    elif field == "contacts":
                        logger.info("Contact change detected")
                    else:
                        logger.info(f"Unhandled field: {field}")

            return JSONResponse({"status": "received", "processed_at": datetime.now().isoformat()})
        else:
            logger.warning(f"Unexpected webhook object: {data.get('object')}")

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}")
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return JSONResponse({"error": "Processing failed", "timestamp": datetime.now().isoformat()}, status_code=500)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "WhatsApp Webhook API is running", "status": "active"}

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Z-Transact API Endpoints
@app.post("/z-transact/upload")
async def upload_document_to_z_transact(request: Request):
    """Upload document to Z-Transact API"""
    if not CONFIG["Z_TRANSACT_ACCESS_TOKEN"] or not CONFIG["Z_TRANSACT_API_URL"]:
        return JSONResponse({
            "status": "error",
            "message": "Z-Transact API configuration missing",
            "timestamp": datetime.now().isoformat()
        }, status_code=500)

    try:
        form = await request.form()
        file = form.get("file")

        if not file:
            return JSONResponse({
                "status": "error",
                "message": "No file provided",
                "timestamp": datetime.now().isoformat()
            }, status_code=400)

        file_content = await file.read()
        filename = file.filename
        mime_type = file.content_type or "application/octet-stream"

        logger.info(f"Uploading document: {filename} ({len(file_content)} bytes)")

        # Upload to Z-Transact
        result = await upload_to_z_transact(file_content, filename, mime_type)

        if result:
            return JSONResponse({
                "status": "success",
                "message": "Document uploaded successfully",
                "data": result,
                "timestamp": datetime.now().isoformat()
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": "Failed to upload document to Z-Transact",
                "timestamp": datetime.now().isoformat()
            }, status_code=500)

    except Exception as e:
        logger.error(f"Document upload error: {e}")
        return JSONResponse({
            "status": "error",
            "message": f"Upload failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)