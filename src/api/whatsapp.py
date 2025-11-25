import httpx
import hashlib
import hmac
import asyncio
from datetime import datetime
from pathlib import Path
from src.config import CONFIG, logger, setup_directories
from src.services.z_transact import upload_to_z_transact, process_z_transact_document
from src.services.z_agent import send_message_to_zagent
from src.services.whatsapp_sender import send_text_message
from src.utils.file_handler import get_file_extension, get_media_subdirectory, generate_safe_filename, validate_file_size

class MediaDownloader:
    @staticmethod
    async def download_media(media_id: str) -> dict | None:
        """Download media from WhatsApp"""
        if not CONFIG["ACCESS_TOKEN"]:
            logger.error("No access token configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get media metadata
                meta_url = f"https://graph.facebook.com/v18.0/{media_id}"
                meta_response = await client.get(
                    meta_url,
                    headers={"Authorization": f"Bearer {CONFIG['ACCESS_TOKEN']}"}
                )

                if meta_response.status_code != 200:
                    logger.error(f"Failed to get media metadata: {meta_response.status_code}")
                    return None

                media_data = meta_response.json()
                media_url = media_data.get("url")

                if not media_url:
                    logger.error("No media URL in response")
                    return None

                # Download the file
                file_response = await client.get(
                    media_url,
                    headers={"Authorization": f"Bearer {CONFIG['ACCESS_TOKEN']}"}
                )

                if file_response.status_code != 200:
                    logger.error(f"File download failed: {file_response.status_code}")
                    return None

                return {
                    "content": file_response.content,
                    "mime_type": media_data.get("mime_type", "unknown"),
                    "file_size": len(file_response.content),
                    "filename": media_data.get("filename"),
                    "download_url": media_url
                }

        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

class MessageProcessor:
    @staticmethod
    async def process_and_upload_media(media_data: dict, phone: str, msg_type: str) -> dict:
        """Process and upload media to Z-Transact"""
        if not validate_file_size(media_data["file_size"], msg_type):
            return {"status": "failed", "error": "File size exceeds limit"}

        # Generate filename and path
        subdirectory = get_media_subdirectory(msg_type, media_data["mime_type"])
        filename = generate_safe_filename(phone, msg_type, media_data["mime_type"], media_data.get("filename"))
        media_base = Path(CONFIG["MEDIA_STORAGE_PATH"])
        file_path = media_base / subdirectory / filename

        # Save file locally
        try:
            with open(file_path, "wb") as f:
                f.write(media_data["content"])
            logger.info(f"File saved: {file_path}")
        except Exception as save_error:
            logger.error(f"File save error: {save_error}")
            return {"status": "failed", "error": f"Save failed: {save_error}"}

        # Upload to Z-Transact
        upload_filename = media_data.get("filename", filename)
        z_transact_result = await upload_to_z_transact(
            media_data["content"], upload_filename, media_data["mime_type"]
        )

        if not z_transact_result:
            return {"status": "failed", "error": "Upload to Z-Transact failed"}

        logger.info("File uploaded to Z-Transact successfully")

        # Process uploaded document
        document_id = z_transact_result.get("id")
        if document_id:
            logger.info(f"Processing document with ID: {document_id}")
            await asyncio.sleep(30)  # Wait before processing
            process_result = await process_z_transact_document(document_id)

            return {
                "status": "success",
                "upload_result": z_transact_result,
                "process_result": process_result,
                "file_path": str(file_path),
                "metadata": {
                    "original_filename": media_data.get("filename"),
                    "saved_filename": filename,
                    "mime_type": media_data["mime_type"],
                    "file_size": media_data["file_size"],
                    "subdirectory": subdirectory
                }
            }

        return {"status": "success", "upload_result": z_transact_result}

async def store_message(phone: str, customer: dict, msg_type: str, content: str, media_data: dict = None):
    """Store message with optional media processing"""
    setup_directories()

    message_data = {
        "phone": phone,
        "customer": customer,
        "type": msg_type,
        "content": content,
        "has_media": media_data is not None,
        "timestamp": datetime.now()
    }

    if media_data:
        result = await MessageProcessor.process_and_upload_media(media_data, phone, msg_type)
        message_data["media_processing"] = result

    logger.info("Message stored successfully")

async def process_message(data: dict):
    """Process incoming WhatsApp message"""
    if "messages" not in data:
        logger.warning("No messages in data")
        return

    msg = data["messages"][0]
    msg_id = msg.get("id", "unknown")
    msg_type = msg.get("type", "text")
    from_number = msg.get("from", "unknown")

    logger.info(f"Message: {msg_type} from {from_number}")
    logger.info(f"Message ID: {msg_id}")

    # Extract customer info
    customer = {}
    if "contacts" in data:
        contact = data["contacts"][0]
        customer = {
            "wa_id": contact.get("wa_id", "unknown"),
            "name": contact.get("profile", {}).get("name", "Unknown")
        }
        logger.info(f"Customer: {customer['name']} ({customer['wa_id']})")

    # Extract content and media
    content = ""
    downloaded_media = None

    if msg_type in ["image", "video"]:
        media_data = msg[msg_type]
        content = media_data.get("caption", "")
        downloaded_media = await MediaDownloader.download_media(media_data["id"])

    elif msg_type == "text":
        content = msg["text"]["body"]
        logger.info(f"Text: {content[:50]}...")

    elif msg_type in ["audio", "document", "sticker"]:
        media_data = msg[msg_type]
        downloaded_media = await MediaDownloader.download_media(media_data["id"])

    else:
        logger.warning(f"Unknown message type: {msg_type}")

    # Store message
    await store_message(from_number, customer, msg_type, content, downloaded_media)

    # Process text messages with Zagent
    if msg_type == "text" and content.strip():
        await handle_text_message(content, from_number, msg_id)

async def handle_text_message(content: str, from_number: str, original_msg_id: str):
    """Handle text message through Zagent and send reply"""
    try:
        # Get response from Zagent
        zagent_result = await send_message_to_zagent(content)

        if zagent_result and zagent_result.get("success", False):
            bot_reply = zagent_result["bot_response"]
            logger.info(f"Zagent response: {bot_reply}")

            # Send reply via WhatsApp with context
            reply_sent = await send_text_message(
                phone=from_number,
                text=bot_reply,
                context_message_id=original_msg_id
            )

            if reply_sent:
                logger.info(f"Reply sent to {from_number}")
            else:
                logger.error(f"Failed to send reply to {from_number}")
        else:
            logger.error("Zagent processing failed")
            await send_text_message(
                phone=from_number,
                text="I'm sorry, I couldn't process your message right now. Please try again later.",
                context_message_id=original_msg_id
            )

    except Exception as e:
        logger.error(f"Error handling text message: {e}")
        await send_text_message(
            phone=from_number,
            text="I'm experiencing technical difficulties. Please try again later.",
            context_message_id=original_msg_id
        )

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