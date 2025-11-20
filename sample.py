from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel
import os
import hashlib
import hmac
import httpx
import json
import logging
from datetime import datetime
from pathlib import Path
import magic
import uuid

# Setup with enhanced logging
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
async def get_z_transact_documents(page: int = 1, per_page: int = 10) -> dict | None:
    """Get documents from Z-Transact API"""
    if not CONFIG["Z_TRANSACT_ACCESS_TOKEN"] or not CONFIG["Z_TRANSACT_API_URL"]:
        logger.error("❌ Z-TRANSACT API CONFIGURATION MISSING")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{CONFIG['Z_TRANSACT_API_URL']}/documents"
            params = {"page": page, "per_page": per_page}
            headers = {
                "accept": "application/json",
                "Cookie": f"access_token={CONFIG['Z_TRANSACT_ACCESS_TOKEN']}"
            }

            logger.info(f"📄 FETCHING Z-TRANSACT DOCUMENTS")
            logger.info(f"   - URL: {url}")
            logger.info(f"   - Page: {page}")
            logger.info(f"   - Per Page: {per_page}")

            response = await client.get(url, params=params, headers=headers)
            logger.info(f"📋 Z-TRANSACT API RESPONSE")
            logger.info(f"   - Status Code: {response.status_code}")
            logger.info(f"   - Response Size: {len(response.content)} bytes")

            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ DOCUMENTS FETCHED SUCCESSFULLY")
                logger.info(f"   - Total Documents: {data.get('total', 0)}")
                logger.info(f"   - Current Page: {data.get('page', 1)}")
                logger.info(f"   - Has Next Page: {data.get('has_next_page', False)}")
                return data
            else:
                logger.error(f"❌ Z-TRANSACT API ERROR")
                logger.error(f"   - Status: {response.status_code}")
                logger.error(f"   - Response: {response.text}")
                return None

    except httpx.RequestError as e:
        logger.error(f"❌ Z-TRANSACT NETWORK ERROR")
        logger.error(f"   - Error: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Z-TRANSACT UNEXPECTED ERROR")
        logger.error(f"   - Error: {e}")
        return None

async def get_z_transact_document_file(document_id: int) -> bytes | None:
    """Get file content from Z-Transact document"""
    if not CONFIG["Z_TRANSACT_ACCESS_TOKEN"] or not CONFIG["Z_TRANSACT_API_URL"]:
        logger.error("❌ Z-TRANSACT API CONFIGURATION MISSING")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First get document details to find the file URL
            doc_url = f"{CONFIG['Z_TRANSACT_API_URL']}/documents/{document_id}"
            headers = {
                "accept": "application/json",
                "Cookie": f"access_token={CONFIG['Z_TRANSACT_ACCESS_TOKEN']}"
            }

            logger.info(f"🔍 FETCHING DOCUMENT DETAILS")
            logger.info(f"   - Document ID: {document_id}")
            logger.info(f"   - URL: {doc_url}")

            doc_response = await client.get(doc_url, headers=headers)

            if doc_response.status_code == 200:
                doc_data = doc_response.json()
                logger.info(f"✅ DOCUMENT DETAILS FETCHED")
                logger.info(f"   - Name: {doc_data.get('name', 'unknown')}")
                logger.info(f"   - Format: {doc_data.get('format', 'unknown')}")
                logger.info(f"   - Status: {doc_data.get('status', 'unknown')}")

                # Note: Based on the API structure, we might need to find the actual file download URL
                # For now, let's return a placeholder or try common download patterns
                file_urls_to_try = [
                    f"{CONFIG['Z_TRANSACT_API_URL']}/documents/{document_id}/file",
                    f"{CONFIG['Z_TRANSACT_API_URL']}/documents/{document_id}/download",
                    f"{CONFIG['Z_TRANSACT_API_URL']}/files/{document_id}",
                ]

                for file_url in file_urls_to_try:
                    logger.info(f"📁 TRYING FILE URL: {file_url}")
                    file_response = await client.get(file_url, headers=headers)

                    if file_response.status_code == 200:
                        logger.info(f"✅ FILE DOWNLOADED SUCCESSFULLY")
                        logger.info(f"   - File Size: {len(file_response.content)} bytes")
                        return file_response.content
                    else:
                        logger.warning(f"⚠️  File URL failed: {file_url} (Status: {file_response.status_code})")

                logger.error(f"❌ NO FILE DOWNLOAD URL FOUND FOR DOCUMENT {document_id}")
                return None
            else:
                logger.error(f"❌ DOCUMENT DETAILS ERROR")
                logger.error(f"   - Status: {doc_response.status_code}")
                logger.error(f"   - Response: {doc_response.text}")
                return None

    except httpx.RequestError as e:
        logger.error(f"❌ Z-TRANSACT FILE NETWORK ERROR")
        logger.error(f"   - Error: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Z-TRANSACT FILE UNEXPECTED ERROR")
        logger.error(f"   - Error: {e}")
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
    """Download media from WhatsApp with enhanced logging - returns dict with file data and metadata"""
    logger.info(f"🌐 DOWNLOADING MEDIA FROM WHATSAPP")
    logger.info(f"   - Media ID: {media_id}")
    logger.info(f"   - Has Access Token: {'Yes' if CONFIG['ACCESS_TOKEN'] else 'No'}")

    if not CONFIG["ACCESS_TOKEN"]:
        logger.error(f"❌ NO ACCESS TOKEN CONFIGURED")
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get media URL
            logger.info(f"🔗 REQUESTING MEDIA METADATA...")
            meta_url = f"https://graph.facebook.com/v18.0/{media_id}"
            logger.info(f"   - URL: {meta_url}")

            resp = await client.get(
                meta_url,
                headers={"Authorization": f"Bearer {CONFIG['ACCESS_TOKEN']}"}
            )

            logger.info(f"📋 METADATA RESPONSE")
            logger.info(f"   - Status Code: {resp.status_code}")
            logger.info(f"   - Response Size: {len(resp.content)} bytes")

            if resp.status_code != 200:
                logger.error(f"❌ METADATA REQUEST FAILED")
                logger.error(f"   - Status: {resp.status_code}")
                logger.error(f"   - Response: {resp.text}")
                return None

            try:
                media_data = resp.json()
                media_url = media_data.get("url")
                mime_type = media_data.get("mime_type", "unknown")
                file_size = media_data.get("file_size", 0)
                filename = media_data.get("filename", None)

                logger.info(f"✅ METADATA PARSED SUCCESSFULLY")
                logger.info(f"   - Media URL: {media_url[:50]}..." if media_url else "None")
                logger.info(f"   - MIME Type: {mime_type}")
                logger.info(f"   - File Size: {file_size} bytes")
                logger.info(f"   - Filename: {filename}")

                if not media_url:
                    logger.error(f"❌ NO MEDIA URL IN RESPONSE")
                    logger.error(f"   - Response Data: {json.dumps(media_data, indent=2)}")
                    return None

                # Download file
                logger.info(f"⬇️  DOWNLOADING MEDIA FILE...")
                start_time = datetime.now()

                file_resp = await client.get(
                    media_url,
                    headers={"Authorization": f"Bearer {CONFIG['ACCESS_TOKEN']}"}
                )

                end_time = datetime.now()
                download_duration = (end_time - start_time).total_seconds()

                logger.info(f"📁 FILE DOWNLOAD RESPONSE")
                logger.info(f"   - Status Code: {file_resp.status_code}")
                logger.info(f"   - Download Time: {download_duration:.2f} seconds")
                logger.info(f"   - File Size: {len(file_resp.content)} bytes")

                if file_resp.status_code == 200:
                    file_content = file_resp.content
                    logger.info(f"✅ MEDIA DOWNLOAD SUCCESSFUL")
                    logger.info(f"   - File Size: {len(file_content)} bytes")
                    logger.info(f"   - Download Speed: {len(file_content) / download_duration:.2f} bytes/sec")

                    # Detect actual file type using python-magic
                    try:
                        detected_mime = magic.from_buffer(file_content, mime=True)
                        logger.info(f"   - Detected MIME: {detected_mime}")
                        if detected_mime and detected_mime != "application/octet-stream":
                            mime_type = detected_mime
                    except Exception as e:
                        logger.warning(f"   - Magic detection failed: {e}")

                    return {
                        "content": file_content,
                        "mime_type": mime_type,
                        "file_size": len(file_content),
                        "filename": filename,
                        "download_url": media_url
                    }
                else:
                    logger.error(f"❌ FILE DOWNLOAD FAILED")
                    logger.error(f"   - Status: {file_resp.status_code}")
                    logger.error(f"   - Response: {file_resp.text}")
                    return None

            except json.JSONDecodeError as e:
                logger.error(f"❌ METADATA JSON PARSE ERROR")
                logger.error(f"   - Error: {e}")
                logger.error(f"   - Response: {resp.text}")
                return None

    except httpx.TimeoutException:
        logger.error(f"❌ DOWNLOAD TIMEOUT")
        logger.error(f"   - Request timed out after 30 seconds")
        return None

    except httpx.RequestError as e:
        logger.error(f"❌ NETWORK REQUEST ERROR")
        logger.error(f"   - Error: {e}")
        logger.error(f"   - Error Type: {type(e).__name__}")
        return None

    except Exception as e:
        logger.error(f"❌ UNEXPECTED DOWNLOAD ERROR")
        logger.error(f"   - Error: {e}")
        logger.error(f"   - Error Type: {type(e).__name__}")
        logger.exception("Full traceback:")
        return None

async def process_message(data: dict):
    """Process incoming message with enhanced logging"""
    logger.info(f"🔄 PROCESSING MESSAGE DATA")
    logger.info(f"   - Data Keys: {list(data.keys())}")

    if "messages" not in data:
        logger.warning(f"⚠️  NO MESSAGES IN DATA")
        logger.warning(f"   - Available keys: {list(data.keys())}")
        return

    messages = data["messages"]
    logger.info(f"   - Message Count: {len(messages)}")

    msg = messages[0]
    msg_id = msg.get("id", "unknown")
    msg_type = msg.get("type", "text")
    from_number = msg.get("from", "unknown")
    timestamp = msg.get("timestamp", "unknown")

    logger.info(f"📩 MESSAGE DETAILS")
    logger.info(f"   - Message ID: {msg_id}")
    logger.info(f"   - From: {from_number}")
    logger.info(f"   - Type: {msg_type}")
    logger.info(f"   - Timestamp: {timestamp}")
    logger.info(f"   - Human Time: {datetime.fromtimestamp(int(timestamp)).isoformat() if timestamp.isdigit() else 'unknown'}")

    # Extract customer info
    customer = {}
    if "contacts" in data:
        logger.info(f"👥 CUSTOMER INFORMATION FOUND")
        contact = data["contacts"][0]
        customer = {
            "wa_id": contact.get("wa_id", "unknown"),
            "name": contact.get("profile", {}).get("name", "Unknown")
        }
        logger.info(f"   - WhatsApp ID: {customer['wa_id']}")
        logger.info(f"   - Name: {customer['name']}")
    else:
        logger.info(f"ℹ️  NO CUSTOMER INFORMATION")

    # Extract content based on type
    content = ""
    downloaded_media = None
    media_id = None
    media_details = {}

    if msg_type in ["image", "video"]:
        logger.info(f"📎 MEDIA MESSAGE PROCESSING")
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

        logger.info(f"   - Media ID: {media_id}")
        logger.info(f"   - Caption: {content}")
        logger.info(f"   - MIME Type: {media_details['mime_type']}")
        logger.info(f"   - File Size: {media_details['file_size']} bytes")
        logger.info(f"   - SHA256: {media_details['sha256'][:16]}...")

        logger.info(f"⬇️  DOWNLOADING MEDIA...")
        downloaded_media = await download_media(media_id)

    elif msg_type == "text":
        logger.info(f"📝 TEXT MESSAGE PROCESSING")
        content = msg["text"]["body"]
        logger.info(f"   - Text: {content}")
        logger.info(f"   - Length: {len(content)} characters")

    elif msg_type in ["audio", "document", "sticker"]:
        logger.info(f"📁 {msg_type.upper()} MESSAGE PROCESSING")
        media_data = msg[msg_type]
        media_id = media_data["id"]

        # Get additional media details
        mime_type = media_data.get("mime_type", "unknown")
        file_name = media_data.get("filename", f"{msg_type}_{media_id}")
        sha256 = media_data.get("sha256", "unknown")
        file_size = media_data.get("file_size", 0)

        logger.info(f"   - Media ID: {media_id}")
        logger.info(f"   - Type: {msg_type}")
        logger.info(f"   - File Name: {file_name}")
        logger.info(f"   - MIME Type: {mime_type}")
        logger.info(f"   - File Size: {file_size} bytes")
        logger.info(f"   - SHA256: {sha256[:16]}...")

        # Log the download URL construction
        metadata_url = f"https://graph.facebook.com/v18.0/{media_id}"
        logger.info(f"🔗 METADATA URL CONSTRUCTED:")
        logger.info(f"   - Metadata URL: {metadata_url}")
        logger.info(f"   - Requires Auth: Yes (Bearer token needed)")
        logger.info(f"   - Purpose: Get real download URL from WhatsApp")

        # Show example curl command for manual testing
        logger.info(f"📋 MANUAL TEST COMMAND:")
        logger.info(f"   - curl -X GET '{metadata_url}' \\")
        logger.info(f"     -H 'Authorization: Bearer {TOKEN[:50]}...'")

        logger.info(f"⬇️  ATTEMPTING TO DOWNLOAD MEDIA...")
        downloaded_media = await download_media(media_id)

        if downloaded_media:
            logger.info(f"✅ {msg_type.upper()} DOWNLOADED SUCCESSFULLY")
            logger.info(f"   - Downloaded Size: {downloaded_media['file_size']} bytes")
            logger.info(f"   - Detected MIME: {downloaded_media['mime_type']}")
        else:
            logger.warning(f"❌ {msg_type.upper()} DOWNLOAD FAILED")
            downloaded_media = None

    else:
        logger.info(f"❓ UNKNOWN MESSAGE TYPE: {msg_type}")
        logger.info(f"   - Full Message Data: {json.dumps(msg, indent=2)}")

    # Log summary
    logger.info(f"📊 MESSAGE PROCESSING SUMMARY")
    logger.info(f"   - Customer: {customer.get('name', 'Unknown')} ({customer.get('wa_id', 'Unknown')})")
    logger.info(f"   - From: {from_number}")
    logger.info(f"   - Type: {msg_type}")
    logger.info(f"   - Has Content: {'Yes' if content else 'No'}")
    logger.info(f"   - Has Media: {'Yes' if downloaded_media else 'No'}")

    if content:
        preview = content[:50] + "..." if len(content) > 50 else content
        logger.info(f"   - Content Preview: {preview}")

    # Store message
    try:
        await store_message(from_number, customer, msg_type, content, downloaded_media)
        logger.info(f"✅ MESSAGE STORED SUCCESSFULLY")
    except Exception as e:
        logger.error(f"❌ MESSAGE STORAGE FAILED")
        logger.error(f"   - Error: {e}")
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
            logger.info(f"💾 SAVING MEDIA FILE")

            # Validate file size
            if not validate_file_size(media_data["file_size"], msg_type):
                logger.warning(f"⚠️  FILE SIZE EXCEEDS LIMIT: {media_data['file_size']} bytes")
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

                    logger.info(f"✅ FILE SAVED SUCCESSFULLY")
                    logger.info(f"   - File Path: {file_path}")
                    logger.info(f"   - File Size: {media_data['file_size']} bytes")
                    logger.info(f"   - MIME Type: {media_data['mime_type']}")
                    logger.info(f"   - Extension: {get_file_extension(media_data['mime_type'], media_data.get('filename'))}")

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

                    # Additional logging for specific file types
                    if media_data["mime_type"] in [
                        "application/pdf",
                        "application/msword",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "application/vnd.ms-excel",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "text/csv",
                        "text/plain",
                        "application/zip"
                    ]:
                        logger.info(f"📄 BUSINESS DOCUMENT DETECTED")
                        logger.info(f"   - Document Type: {media_data['mime_type']}")
                        if media_data.get("filename"):
                            logger.info(f"   - Original Name: {media_data['filename']}")
                        logger.info(f"   - Storage Location: {subdirectory}/{filename}")

                except Exception as save_error:
                    logger.error(f"❌ FILE SAVE ERROR")
                    logger.error(f"   - Error: {save_error}")
                    logger.error(f"   - File Path: {file_path}")
                    message_data["media_error"] = f"Save failed: {save_error}"
                    message_data["has_media"] = False

        # Log message storage details
        logger.info(f"📋 MESSAGE STORAGE SUMMARY")
        logger.info(f"   - Phone: {phone}")
        logger.info(f"   - Customer: {customer.get('name', 'Unknown')}")
        logger.info(f"   - Type: {msg_type}")
        logger.info(f"   - Has Content: {'Yes' if content else 'No'}")
        logger.info(f"   - Has Media: {'Yes' if message_data['has_media'] else 'No'}")

        if message_data["media_file_path"]:
            logger.info(f"   - Media Path: {message_data['media_file_path']}")
        if message_data.get("media_metadata"):
            metadata = message_data["media_metadata"]
            logger.info(f"   - Media Extension: {metadata['extension']}")
            logger.info(f"   - Media Size: {metadata['file_size']} bytes")

        # Here you would typically save to a database
        # await save_to_database(message_data)
        logger.info(f"🗄️  MESSAGE DATA READY FOR DATABASE STORAGE")
        logger.debug(f"   - Data: {json.dumps(message_data, indent=2, default=str)}")

        logger.info(f"✅ MESSAGE PROCESSING COMPLETED SUCCESSFULLY")

    except Exception as e:
        logger.error(f"❌ MESSAGE STORAGE ERROR")
        logger.error(f"   - Error: {e}")
        logger.error(f"   - Error Type: {type(e).__name__}")
        logger.exception("Full traceback:")
        raise

# Routes
@app.get(CONFIG["WEBHOOK_URL"])
async def verify_webhook(request: Request):
    """Verify webhook endpoint with enhanced logging"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    # Log webhook verification attempt
    logger.info(f"🔍 WEBHOOK VERIFICATION ATTEMPT")
    logger.info(f"   - Client IP: {client_ip}")
    logger.info(f"   - User Agent: {user_agent}")
    logger.info(f"   - Mode: {mode}")
    logger.info(f"   - Token Provided: {'Yes' if token else 'No'}")
    logger.info(f"   - Provided Token: {token}")
    logger.info(f"   - Expected Token: {CONFIG['VERIFY_TOKEN']}")
    logger.info(f"   - Token Match: {token == CONFIG['VERIFY_TOKEN']}")
    logger.info(f"   - Challenge: {challenge}")
    logger.info(f"   - YOUR_VERIFY_TOKEN ENV: {YOUR_VERIFY_TOKEN}")
    logger.info(f"   - VERSION: {VERSION}")
    logger.info(f"   - PHONE_NUMBER_ID: {PHONE_NUMBER_ID}")

    if mode == "subscribe" and token == CONFIG["VERIFY_TOKEN"]:
        logger.info(f"✅ WEBHOOK VERIFICATION SUCCESSFUL")
        logger.info(f"   - Challenge Response: {challenge}")
        return PlainTextResponse(challenge)

    logger.warning(f"❌ WEBHOOK VERIFICATION FAILED")
    logger.warning(f"   - Mode Mismatch: {mode} != subscribe")
    logger.warning(f"   - Token Mismatch: {token} != {CONFIG['VERIFY_TOKEN']}")
    raise HTTPException(status_code=403, detail="Invalid verification")

@app.post(CONFIG["WEBHOOK_URL"])
async def handle_webhook(request: Request):
    """Handle webhook messages with enhanced logging"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    signature = request.headers.get("x-hub-signature-256")
    content_type = request.headers.get("content-type", "unknown")

    body = await request.body()

    # Log incoming webhook request
    logger.info(f"📨 INCOMING WEBHOOK REQUEST")
    logger.info(f"   - Client IP: {client_ip}")
    logger.info(f"   - User Agent: {user_agent}")
    logger.info(f"   - Content Type: {content_type}")
    logger.info(f"   - Signature: {signature}")
    logger.info(f"   - Body Size: {len(body)} bytes")
    logger.info(f"   - Timestamp: {datetime.now().isoformat()}")

    # Skip signature verification for POST requests
    logger.info(f"⏭️  SIGNATURE VERIFICATION SKIPPED")
    logger.info(f"   - POST webhook processes messages directly")

    logger.info(f"✅ WEBHOOK REQUEST ACCEPTED FOR PROCESSING")

    # Process webhook
    try:
        data = json.loads(body)
        logger.info(f"📋 WEBHOOK DATA PARSED")
        logger.info(f"   - Object: {data.get('object', 'unknown')}")
        logger.info(f"   - Entry Count: {len(data.get('entry', []))}")

        if data.get("object") == "whatsapp_business_account":
            logger.info(f"📱 WHATSAPP BUSINESS ACCOUNT WEBHOOK")

            for i, entry in enumerate(data.get("entry", [])):
                logger.info(f"   - Entry {i+1}: ID={entry.get('id', 'unknown')}")

                for j, change in enumerate(entry.get("changes", [])):
                    field = change.get("field", "unknown")
                    logger.info(f"     - Change {j+1}: Field={field}")

                    if field == "messages":
                        logger.info(f"📨 PROCESSING MESSAGE CHANGE")
                        await process_message(change.get("value", {}))
                    elif field == "contacts":
                        logger.info(f"👤 PROCESSING CONTACT CHANGE")
                        # Could add contact processing here
                    else:
                        logger.info(f"ℹ️  UNHANDLED FIELD: {field}")

            logger.info(f"✅ WEBHOOK PROCESSING COMPLETED")
            return JSONResponse({"status": "received", "processed_at": datetime.now().isoformat()})

        else:
            logger.warning(f"⚠️  UNEXPECTED WEBHOOK OBJECT: {data.get('object')}")
            logger.warning(f"   - Expected: whatsapp_business_account")

    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON PARSE ERROR")
        logger.error(f"   - Error: {e}")
        logger.error(f"   - Body Preview: {body[:200]}...")
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    except Exception as e:
        logger.error(f"❌ WEBHOOK PROCESSING ERROR")
        logger.error(f"   - Error: {e}")
        logger.error(f"   - Error Type: {type(e).__name__}")
        logger.error(f"   - Body: {body}")
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
@app.get("/z-transact/documents")
async def list_documents(page: int = 1, per_page: int = 10):
    """List documents from Z-Transact API"""
    documents = await get_z_transact_documents(page, per_page)
    if documents:
        return JSONResponse({
            "status": "success",
            "data": documents,
            "timestamp": datetime.now().isoformat()
        })
    else:
        return JSONResponse({
            "status": "error",
            "message": "Failed to fetch documents from Z-Transact API",
            "timestamp": datetime.now().isoformat()
        }, status_code=500)

@app.get("/z-transact/documents/{document_id}")
async def get_document_details(document_id: int):
    """Get specific document details from Z-Transact API"""
    if not CONFIG["Z_TRANSACT_ACCESS_TOKEN"] or not CONFIG["Z_TRANSACT_API_URL"]:
        return JSONResponse({
            "status": "error",
            "message": "Z-Transact API configuration missing",
            "timestamp": datetime.now().isoformat()
        }, status_code=500)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{CONFIG['Z_TRANSACT_API_URL']}/documents/{document_id}"
            headers = {
                "accept": "application/json",
                "Cookie": f"access_token={CONFIG['Z_TRANSACT_ACCESS_TOKEN']}"
            }

            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return JSONResponse({
                    "status": "success",
                    "data": response.json(),
                    "timestamp": datetime.now().isoformat()
                })
            else:
                return JSONResponse({
                    "status": "error",
                    "message": f"Document {document_id} not found",
                    "timestamp": datetime.now().isoformat()
                }, status_code=404)

    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": f"Error fetching document: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }, status_code=500)

@app.get("/z-transact/documents/{document_id}/download")
async def download_document_file(document_id: int):
    """Download document file from Z-Transact API"""
    file_content = await get_z_transact_document_file(document_id)
    if file_content:
        # Try to get document details for filename
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{CONFIG['Z_TRANSACT_API_URL']}/documents/{document_id}"
                headers = {
                    "accept": "application/json",
                    "Cookie": f"access_token={CONFIG['Z_TRANSACT_ACCESS_TOKEN']}"
                }
                doc_response = await client.get(url, headers=headers)
                if doc_response.status_code == 200:
                    doc_data = doc_response.json()
                    filename = doc_data.get('name', f'document_{document_id}')
                    format_type = doc_data.get('format', 'pdf')
                    if not filename.endswith(f'.{format_type}'):
                        filename = f"{filename}.{format_type}"
                else:
                    filename = f"document_{document_id}.pdf"
        except:
            filename = f"document_{document_id}.pdf"

        return Response(
            content=file_content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        return JSONResponse({
            "status": "error",
            "message": f"Failed to download document {document_id}",
            "timestamp": datetime.now().isoformat()
        }, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)