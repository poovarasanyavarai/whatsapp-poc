import httpx
import json
from src.config import CONFIG, logger

class ZAgentAPI:
    @staticmethod
    async def _make_request(endpoint: str, payload: dict = None, method: str = "POST") -> dict:
        """Generic method for making ZAgent API requests"""
        url = f"{CONFIG['ZAGENT_API_URL']}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {CONFIG['ZAGENT_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
            "accept": "application/json, text/plain, */*"
        }

        logger.info(f"ZAGENT API REQUEST - {method} {url}")
        if payload:
            logger.info(f"  Payload: {json.dumps(payload, indent=2)}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(method, url, json=payload, headers=headers)
                response_data = response.json()

                logger.info(f"ZAGENT API RESPONSE:")
                logger.info(f"  Status: {response.status_code}")
                logger.info(f"  Response: {json.dumps(response_data, indent=2)}")

                return {
                    "success": response.status_code in [200, 201],
                    "status_code": response.status_code,
                    "data": response_data
                }

        except Exception as e:
            logger.error(f"ZAgent API error: {e}")
            return {"success": False, "error": str(e)}

async def send_message_to_zagent(message: str) -> dict:
    """Send message to ZAgent for processing"""
    endpoint = f"chatbot/{CONFIG['ZAGENT_BOT_UUID']}/conversation/{CONFIG['ZAGENT_CONVERSATION_ID']}/chat/completions"

    payload = {
        "messages": [{"role": "user", "content": message}],
        "stream": False,
        "use_context": True,
        "time_zone": "Asia/Calcutta"
    }

    result = await ZAgentAPI._make_request(endpoint, payload)

    if result["success"]:
        data = result["data"]

        # Extract content from response
        content = ""
        if "message" in data and "content" in data["message"]:
            content = data["message"]["content"]

        return {
            "success": True,
            "bot_response": content,
            "message_id": data.get("message", {}).get("id"),
            "full_response": data
        }
    else:
        return {
            "success": False,
            "error": result.get("error", "ZAgent API failed")
        }

async def test_zagent_connection() -> dict:
    """Test ZAgent API connection"""
    return await ZAgentAPI._make_request(f"bots/{CONFIG['ZAGENT_BOT_UUID']}")