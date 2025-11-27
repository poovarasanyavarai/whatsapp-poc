import httpx
import hashlib
import hmac
import json
import asyncio
from datetime import datetime
from pathlib import Path
from src.config import CONFIG, logger, ensure_media_directory
from src.services.z_transact import upload_to_z_transact, process_z_transact_document
from src.utils.file_handler import get_file_extension, get_media_subdirectory, generate_safe_filename, validate_file_size

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

                    # Upload ALL file types to Z-Transact
                    logger.info(f"Uploading to Z-Transact: {media_data['mime_type']}")

                    # Get original filename or use saved filename
                    upload_filename = media_data.get("filename", filename)
                    if not upload_filename:
                        upload_filename = filename

                    # Upload to Z-Transact
                    z_transact_result = await upload_to_z_transact(
                        media_data["content"],
                        upload_filename,
                        media_data["mime_type"]
                    )

                    if z_transact_result:
                        logger.info(f"File uploaded to Z-Transact successfully")
                        message_data["z_transact_upload"] = {
                            "status": "success",
                            "upload_result": z_transact_result,
                            "upload_filename": upload_filename
                        }

                        # Process the uploaded document
                        document_id = z_transact_result.get("id")
                        if document_id:
                            logger.info(f"Waiting 60 seconds before processing document with ID: {document_id}")
                            await asyncio.sleep(60)  # Wait 30 seconds before calling process API
                            logger.info(f"Processing uploaded document with ID: {document_id}")
                            process_result = await process_z_transact_document(document_id)
                            if process_result:
                                logger.info(f"Document processed successfully: {process_result}")
                                message_data["z_transact_process"] = {
                                    "status": "success",
                                    "process_result": process_result
                                }
                            else:
                                logger.error(f"Failed to process document with ID: {document_id}")
                                message_data["z_transact_process"] = {
                                    "status": "failed",
                                    "error": "Process API call failed"
                                }
                        else:
                            logger.error(f"No document ID found in upload result: {z_transact_result}")
                    else:
                        logger.error(f"Failed to upload file to Z-Transact")
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
    logger.info(f"#@#@#{msg_id}")

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