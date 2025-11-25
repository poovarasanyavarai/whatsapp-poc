from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
import os
import json
from datetime import datetime

# Import modules from new structure
from src.api.whatsapp import process_message, verify_signature
from src.services.z_agent import send_message_to_zagent, test_zagent_connection
from src.config import logger

app = FastAPI(title="WhatsApp Webhook API", version="1.0.0")

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

@app.get("/test/zagent")
async def test_zagent():
    """Test Zagent API connection"""
    is_connected = await test_zagent_connection()
    return {
        "status": "success" if is_connected else "failed",
        "zagent_connected": is_connected,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/test/zagent/message")
async def test_zagent_message(request: dict):
    """Send test message to Zagent API"""
    message = request.get("message", "Hello, this is a test message")
    conversation_id = request.get("conversation_id")

    result = await send_message_to_zagent(message, conversation_id)

    if result and result.get("success", False):
        return {
            "status": "success",
            "message": "Message processed successfully",
            "user_input": message,
            "bot_reply": result["bot_response"],
            "response_details": {
                "message_id": result.get("message_id"),
                "end": result.get("end"),
                "end_reason": result.get("end_reason"),
                "time_taken": result.get("time_taken"),
                "should_connect_agent": result.get("should_connect_agent")
            },
            "timestamp": datetime.now().isoformat()
        }
    else:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to process message with Zagent",
                "error_details": result.get("error", "Unknown error") if result else "No response from Zagent",
                "timestamp": datetime.now().isoformat()
            }
        )

@app.post("/test/echo")
async def test_echo(request: dict):
    """Simple echo endpoint for testing response format"""
    user_message = request.get("message", "Hello")
    return {
        "status": "success",
        "user_input": user_message,
        "bot_reply": f"Echo: {user_message}",
        "response_details": {
            "message_id": 12345,
            "end": True,
            "end_reason": "completed",
            "time_taken": 0.1,
            "should_connect_agent": False
        },
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)