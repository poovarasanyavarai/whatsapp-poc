import httpx
import json
import asyncio
from src.config import CONFIG, logger

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

async def process_z_transact_document(document_id: int) -> dict | None:
    """Process uploaded document in Z-Transact API using the specified format"""
    if not CONFIG["Z_TRANSACT_ACCESS_TOKEN"] or not CONFIG["Z_TRANSACT_API_URL"]:
        logger.error("Z-Transact API configuration missing")
        return None

    url = f"{CONFIG['Z_TRANSACT_API_URL']}/documents/process"

    # Prepare request payload exactly as specified
    payload = {
        "document_ids": [
            document_id
        ]
    }

    logger.info(f"Processing Z-Transact document: {document_id}")

    try:
        headers_cookie = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        cookies = {
            "access_token": CONFIG["Z_TRANSACT_ACCESS_TOKEN"]
        }

        logger.info(f"Trying cookie authentication (fallback)")
        logger.info(f"Request headers: {json.dumps(headers_cookie)}")
        logger.info(f"Request cookies: access_token={CONFIG['Z_TRANSACT_ACCESS_TOKEN'][:20]}...")

        async with httpx.AsyncClient(timeout=60.0, headers=headers_cookie, cookies=cookies) as client:
            response = await client.post(url, json=payload)

            logger.info(f"Cookie authentication response status: {response.status_code}")
            logger.info(f"Cookie authentication response headers: {dict(response.headers)}")

            if response.status_code == 200 or response.status_code == 201:
                result = response.json()
                logger.info(f"Success with cookie authentication: {result}")

                # Check if processing was successful
                if result.get('success') and document_id in result['success']:
                    logger.info(f"Document {document_id} processed successfully with cookie authentication")
                elif result.get('failed') and document_id in result['failed']:
                    logger.warning(f"Document {document_id} processing failed on Z-Transact side (cookie auth)")
                else:
                    logger.warning(f"Unexpected process response format for document {document_id}")

                return result
            else:
                logger.error(f"Cookie authentication also failed: {response.status_code} - {response.text}")
                return None

    except Exception as e:
        logger.error(f"Cookie authentication attempt failed: {e}")
        return None