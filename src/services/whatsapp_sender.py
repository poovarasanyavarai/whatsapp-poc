import httpx
import json
import os
from src.config import CONFIG, logger

class WhatsAppAPI:
    BASE_URL = "https://graph.facebook.com/v18.0"

    @classmethod
    def _get_credentials(cls):
        """Get API credentials from environment variables"""
        return {
            "token": os.getenv("TOKEN") or CONFIG.get("ACCESS_TOKEN"),
            "phone_number_id": os.getenv("PHONE_NUMBER_ID") or CONFIG.get("PHONE_NUMBER_ID")
        }

    @classmethod
    def _prepare_headers(cls, token: str) -> dict:
        """Prepare API headers"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    @classmethod
    async def _send_request(cls, payload: dict, phone: str = None) -> dict:
        """Send request to WhatsApp API with common error handling"""
        credentials = cls._get_credentials()

        if not credentials["token"] or not credentials["phone_number_id"]:
            logger.error("WhatsApp API configuration missing")
            return {"success": False, "error": "Missing configuration"}

        url = f"{cls.BASE_URL}/{credentials['phone_number_id']}/messages"
        headers = cls._prepare_headers(credentials["token"])

        if phone:
            payload["to"] = phone

        # Log request
        logger.info(f"WHATSAPP API REQUEST:")
        logger.info(f"  URL: {url}")
        logger.info(f"  Payload: {json.dumps(payload, indent=2)}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response_data = response.json()

                # Log response
                logger.info(f"WHATSAPP API RESPONSE:")
                logger.info(f"  Status: {response.status_code}")
                logger.info(f"  Response: {json.dumps(response_data, indent=2)}")

                return {
                    "success": response.status_code == 200,
                    "status_code": response.status_code,
                    "data": response_data,
                    "message_id": response_data.get("messages", [{}])[0].get("id") if response.status_code == 200 else None
                }

        except Exception as e:
            logger.error(f"WhatsApp API error: {e}")
            return {"success": False, "error": str(e)}

async def send_text_message(phone: str, text: str, context_message_id: str = None) -> bool:
    """Send text message with optional context for reply"""
    # Validate input
    if not text or not text.strip():
        logger.error("Cannot send empty message")
        return False

    if not phone or not phone.strip():
        logger.error("Phone number is required")
        return False

    payload = {
        "messaging_product": "whatsapp",
        "type": "text",
        "text": {
            "body": text.strip(),
            "preview_url": False
        }
    }

    if context_message_id:
        payload["context"] = {"message_id": context_message_id}

    result = await WhatsAppAPI._send_request(payload, phone)

    if result["success"]:
        logger.info(f"Message sent successfully - ID: {result['message_id']}")
    else:
        logger.error(f"Failed to send message: {result.get('error', 'Unknown error')}")

    return result["success"]