from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
import os
import json
from datetime import datetime

# Import modules from new structure
from src.api.whatsapp import process_message, verify_signature
from src.config import logger
from src.api.monitoring import router as monitoring_router

app = FastAPI(title="WhatsApp Webhook API", version="1.0.0")

# Include monitoring router
app.include_router(monitoring_router, prefix="/monitor", tags=["monitoring"])

# Models
class WebhookData(BaseModel):
    object: str
    entry: list[dict]

# Routes
@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verify webhook endpoint"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    logger.info(f"Webhook verification from {client_ip}: mode={mode}, token={token}")

    if mode == "subscribe" and token == os.getenv("YOUR_VERIFY_TOKEN"):
        logger.info("Webhook verified successfully")
        return PlainTextResponse(challenge)

    logger.warning("Webhook verification failed")
    raise HTTPException(status_code=403, detail="Invalid verification")

@app.post("/webhook")
async def handle_webhook(request: Request):
    """Handle webhook messages - always return 200 to acknowledge receipt"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    signature = request.headers.get("x-hub-signature-256")
    content_type = request.headers.get("content-type", "unknown")

    body = await request.body()

    logger.info(f"WEBHOOK REQUEST - Client: {client_ip}, User-Agent: {user_agent}, Size: {len(body)} bytes")

    # Initialize response
    response_data = {
        "status": "received",
        "processed_at": datetime.now().isoformat()
    }

    # Skip signature verification for POST requests
    try:
        data = json.loads(body)

        if data.get("object") == "whatsapp_business_account":
            logger.info("WHATSAPP BUSINESS ACCOUNT WEBHOOK")

            for entry in data.get("entry", []):
                entry_id = entry.get('id', 'unknown')
                logger.info(f"PROCESSING ENTRY - ID: {entry_id}")

                for change in entry.get("changes", []):
                    field = change.get("field", "unknown")
                    logger.info(f"PROCESSING CHANGE - Field: {field}")

                    if field == "messages":
                        value = change.get("value", {})

                        # Extract comprehensive message details
                        if "messages" in value:
                            for msg in value.get("messages", []):
                                message_id = msg.get("id", "unknown")
                                from_number = msg.get("from", "unknown")
                                msg_type = msg.get("type", "text")
                                timestamp = msg.get("timestamp", "unknown")

                                logger.info(f"MESSAGE DETAILS:")
                                logger.info(f"  - Message ID: {message_id}")
                                logger.info(f"  - From Number: {from_number}")
                                logger.info(f"  - Message Type: {msg_type}")
                                logger.info(f"  - Timestamp: {timestamp}")
                                logger.info(f"  - Status: received")

                                # Log message content details based on type
                                if msg_type == "text":
                                    text_content = msg.get("text", {}).get("body", "")
                                    logger.info(f"  - Text Content: {text_content[:100]}{'...' if len(text_content) > 100 else ''}")

                                elif msg_type in ["image", "video"]:
                                    media = msg.get(msg_type, {})
                                    caption = media.get("caption", "")
                                    media_id = media.get("id", "unknown")
                                    mime_type = media.get("mime_type", "unknown")
                                    file_size = media.get("file_size", 0)
                                    logger.info(f"  - Media ID: {media_id}")
                                    logger.info(f"  - MIME Type: {mime_type}")
                                    logger.info(f"  - File Size: {file_size} bytes")
                                    logger.info(f"  - Caption: {caption[:100]}{'...' if len(caption) > 100 else ''}")

                                elif msg_type in ["audio", "document", "sticker"]:
                                    media = msg.get(msg_type, {})
                                    media_id = media.get("id", "unknown")
                                    filename = media.get("filename", "")
                                    mime_type = media.get("mime_type", "unknown")
                                    file_size = media.get("file_size", 0)
                                    logger.info(f"  - Media ID: {media_id}")
                                    logger.info(f"  - Filename: {filename}")
                                    logger.info(f"  - MIME Type: {mime_type}")
                                    logger.info(f"  - File Size: {file_size} bytes")

                                # Log contact/customer details if available
                                if "contacts" in value:
                                    for contact in value.get("contacts", []):
                                        contact_name = contact.get("profile", {}).get("name", "Unknown")
                                        contact_wa_id = contact.get("wa_id", "unknown")
                                        logger.info(f"CONTACT DETAILS:")
                                        logger.info(f"  - Name: {contact_name}")
                                        logger.info(f"  - WhatsApp ID: {contact_wa_id}")

                        await process_message(change.get("value", {}))

                    elif field == "message_template_status_update":
                        # Log message template status updates
                        status_update = change.get("value", {})
                        template_name = status_update.get("message_template_name", "unknown")
                        event_type = status_update.get("event_type", "unknown")
                        message_template_status = status_update.get("message_template_status", "unknown")

                        logger.info(f"MESSAGE TEMPLATE STATUS UPDATE:")
                        logger.info(f"  - Template Name: {template_name}")
                        logger.info(f"  - Event Type: {event_type}")
                        logger.info(f"  - Status: {message_template_status}")
                        logger.info(f"  - Status: processed")

                    elif field == "message_sent":
                        # Log message sent confirmations
                        message_sent = change.get("value", {})
                        conversation_id = message_sent.get("conversation_id", "unknown")
                        status = message_sent.get("status", "unknown")
                        pricing = message_sent.get("pricing", {})

                        logger.info(f"MESSAGE SENT CONFIRMATION:")
                        logger.info(f"  - Conversation ID: {conversation_id}")
                        logger.info(f"  - Status: {status}")
                        logger.info(f"  - Pricing Model: {pricing.get('pricing_model', 'unknown')}")
                        logger.info(f"  - Billable: {pricing.get('billable', 'unknown')}")
                        logger.info(f"  - Status: processed")

                    elif field == "contacts":
                        logger.info("CONTACT CHANGE DETECTED")
                        contacts = change.get("value", {}).get("contacts", [])
                        for contact in contacts:
                            contact_name = contact.get("profile", {}).get("name", "Unknown")
                            contact_wa_id = contact.get("wa_id", "unknown")
                            logger.info(f"  - Name: {contact_name}, WhatsApp ID: {contact_wa_id}")

                    else:
                        logger.info(f"UNHANDLED FIELD: {field}")

        else:
            logger.warning(f"UNEXPECTED WEBHOOK OBJECT: {data.get('object')}")
            response_data["status"] = "invalid_object"
            response_data["object"] = data.get("object")

    except json.JSONDecodeError as e:
        logger.error(f"JSON PARSE ERROR: {e}")
        response_data["status"] = "json_error"
        response_data["error"] = str(e)

    except Exception as e:
        logger.error(f"WEBHOOK PROCESSING ERROR: {e}")
        response_data["status"] = "processing_error"
        response_data["error"] = str(e)

    # Log final webhook response
    logger.info(f"WEBHOOK RESPONSE - Status: {response_data['status']}, Processed At: {response_data['processed_at']}")

    # Always return 200 to acknowledge webhook receipt
    return JSONResponse(response_data)

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "WhatsApp Webhook API is running", "status": "active"}

@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)