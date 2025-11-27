import asyncio
from typing import Dict, Optional
from datetime import datetime
import httpx
from pathlib import Path
from src.config import CONFIG, logger, ensure_media_directory
from src.utils.message_deduplicator import message_deduplicator
from src.services.z_transact import upload_to_z_transact, process_z_transact_document
from src.utils.file_handler import get_file_extension, get_media_subdirectory, generate_safe_filename, validate_file_size

class MediaProcessor:
    """Asynchronous media processing to prevent webhook timeouts"""

    def __init__(self):
        self.processing_queue: asyncio.Queue = asyncio.Queue()
        self.is_processing = False

    async def start_processing(self):
        """Start background media processing"""
        if not self.is_processing:
            self.is_processing = True
            asyncio.create_task(self._process_media_queue())

    async def queue_media_for_processing(self, message_data: dict, media_id: str, msg_type: str, content: str, customer: dict):
        """Queue media for async processing"""
        try:
            # Check for duplicates
            if message_deduplicator.is_duplicate(message_data):
                logger.info(f"Duplicate message detected, skipping: {message_data.get('id')}")
                return

            processing_data = {
                "message_data": message_data,
                "media_id": media_id,
                "msg_type": msg_type,
                "content": content,
                "customer": customer,
                "timestamp": datetime.now(),
                "status": "queued"
            }

            await self.processing_queue.put(processing_data)
            logger.info(f"Media queued for async processing: {media_id}")

            # Start processing if not already running
            await self.start_processing()

        except Exception as e:
            logger.error(f"Failed to queue media for processing: {e}")

    async def _process_media_queue(self):
        """Background task to process media queue"""
        logger.info("Started background media processing")

        while self.is_processing or not self.processing_queue.empty():
            try:
                # Get media processing task with timeout
                processing_data = await asyncio.wait_for(self.processing_queue.get(), timeout=1.0)
                await self._process_single_media(processing_data)

            except asyncio.TimeoutError:
                # No items in queue, continue
                continue
            except Exception as e:
                logger.error(f"Error in media processing queue: {e}")
                await asyncio.sleep(1)  # Prevent rapid error loops

        logger.info("Background media processing stopped")

    async def _process_single_media(self, processing_data: dict):
        """Process a single media item"""
        media_id = processing_data["media_id"]
        message_data = processing_data["message_data"]

        try:
            logger.info(f"Starting async media processing: {media_id}")
            processing_data["status"] = "downloading"

            # Download media
            downloaded_media = await self._download_media(media_id)
            if not downloaded_media:
                logger.error(f"Failed to download media: {media_id}")
                processing_data["status"] = "download_failed"
                return

            processing_data["status"] = "processing"

            # Process and store media
            await self._store_media_data(
                phone=message_data["from"],
                customer=processing_data["customer"],
                msg_type=processing_data["msg_type"],
                content=processing_data["content"],
                media_data=downloaded_media,
                processing_data=processing_data
            )

            processing_data["status"] = "completed"
            logger.info(f"Media processing completed: {media_id}")

        except Exception as e:
            logger.error(f"Media processing failed: {media_id}, Error: {e}")
            processing_data["status"] = "failed"
            processing_data["error"] = str(e)

    async def _download_media(self, media_id: str) -> Optional[dict]:
        """Download media from WhatsApp with proper timeout and error handling"""
        logger.info(f"🔍 META API: Starting media download for ID: {media_id}")

        if not CONFIG.get("TOKEN"):
            logger.error("❌ META API: No WhatsApp access token configured")
            return None

        try:
            timeout = httpx.Timeout(10.0, connect=5.0)  # 10s total, 5s connect

            async with httpx.AsyncClient(timeout=timeout) as client:
                # Get media URL
                meta_url = f"https://graph.facebook.com/v18.0/{media_id}"
                logger.info(f"🌐 META API: Requesting media metadata - URL: {meta_url}")

                meta_resp = await client.get(
                    meta_url,
                    headers={"Authorization": f"Bearer {CONFIG['TOKEN']}"}
                )

                logger.info(f"📊 META API: Metadata response - Status: {meta_resp.status_code}, Headers: {dict(meta_resp.headers)}")

                if meta_resp.status_code != 200:
                    logger.error(f"❌ META API: Failed to get media metadata - Status: {meta_resp.status_code}, Response: {meta_resp.text[:200]}")
                    return None

                media_data = meta_resp.json()
                media_url = media_data.get("url")
                mime_type = media_data.get("mime_type", "unknown")
                file_size = media_data.get("file_size", 0)
                filename = media_data.get("filename", None)

                logger.info(f"📋 META API: Media metadata received - ID: {media_id}, MIME: {mime_type}, Size: {file_size}, Filename: {filename}")
                logger.info(f"🔗 META API: Media download URL: {media_url[:100] if media_url else 'None'}...")

                if not media_url:
                    logger.error("❌ META API: No media URL in metadata response")
                    return None

                # Download file with separate timeout
                logger.info(f"⬇️  META API: Starting file download for {media_id}")
                file_resp = await client.get(
                    media_url,
                    headers={"Authorization": f"Bearer {CONFIG['TOKEN']}"},
                    timeout=httpx.Timeout(30.0, connect=5.0)  # 30s for file download
                )

                logger.info(f"📊 META API: File download response - Status: {file_resp.status_code}, Headers: {dict(file_resp.headers)}")

                if file_resp.status_code == 200:
                    file_content = file_resp.content
                    logger.info(f"✅ META API: Media downloaded successfully - ID: {media_id}, Size: {len(file_content)} bytes, Content-Type: {file_resp.headers.get('content-type', 'unknown')}")

                    return {
                        "content": file_content,
                        "mime_type": mime_type,
                        "file_size": len(file_content),
                        "filename": filename,
                        "download_url": media_url
                    }
                else:
                    logger.error(f"❌ META API: File download failed - Status: {file_resp.status_code}, Response: {file_resp.text[:200]}")
                    return None

        except asyncio.TimeoutError:
            logger.error(f"⏱️  META API: Download timeout for media: {media_id}")
            return None
        except Exception as e:
            logger.error(f"💥 META API: Download error for media {media_id}: {e}")
            return None

    async def _store_media_data(self, phone: str, customer: dict, msg_type: str, content: str, media_data: dict, processing_data: dict):
        """Store media data and upload to Z-Transact"""
        try:
            ensure_media_directory()

            # Validate file size
            if not validate_file_size(media_data["file_size"], msg_type):
                logger.warning(f"File too large: {media_data['file_size']} bytes")
                return

            # Determine subdirectory and generate filename
            subdirectory = get_media_subdirectory(msg_type, media_data["mime_type"])
            filename = generate_safe_filename(
                phone, msg_type, media_data["mime_type"], media_data.get("filename")
            )

            # Create full file path
            media_base = Path(CONFIG["MEDIA_STORAGE_PATH"])
            file_path = media_base / subdirectory / filename

            # Save file to disk
            with open(file_path, "wb") as f:
                f.write(media_data["content"])

            logger.info(f"File saved: {file_path}")
            processing_data["file_path"] = str(file_path)

            # Upload to Z-Transact with timeout protection
            upload_filename = media_data.get("filename", filename)
            if not upload_filename:
                upload_filename = filename

            logger.info(f"🔄 MEDIA PROCESSOR: Starting Z-Transact upload - File: {upload_filename}, Path: {file_path}")
            processing_data["status"] = "uploading"

            # Upload with timeout
            z_transact_result = await asyncio.wait_for(
                upload_to_z_transact(
                    media_data["content"],
                    upload_filename,
                    media_data["mime_type"]
                ),
                timeout=30.0  # 30 second timeout for upload
            )

            if z_transact_result:
                document_id = z_transact_result.get("id", "unknown")
                logger.info(f"✅ MEDIA PROCESSOR: Z-Transact upload completed successfully - Document ID: {document_id}")
                processing_data["z_transact_upload"] = "success"
                processing_data["z_transact_result"] = z_transact_result
                processing_data["document_id"] = document_id

                # Process the uploaded document
                if document_id:
                    processing_data["status"] = "processing_z_transact"
                    logger.info(f"⏳ MEDIA PROCESSOR: Waiting 30 seconds before processing document ID: {document_id}")

                    try:
                        # Wait before processing
                        await asyncio.sleep(30)

                        logger.info(f"🔄 MEDIA PROCESSOR: Starting document processing for ID: {document_id}")
                        process_result = await asyncio.wait_for(
                            process_z_transact_document(document_id),
                            timeout=30.0
                        )

                        if process_result:
                            logger.info(f"✅ MEDIA PROCESSOR: Document processed successfully - Result: {process_result}")
                            processing_data["z_transact_process"] = "success"
                            processing_data["process_result"] = process_result
                        else:
                            logger.error(f"❌ MEDIA PROCESSOR: Failed to process document ID: {document_id}")
                            processing_data["z_transact_process"] = "failed"

                    except asyncio.TimeoutError:
                        logger.error(f"⏱️  MEDIA PROCESSOR: Document processing timeout for ID: {document_id}")
                        processing_data["z_transact_process"] = "timeout"
                    except Exception as e:
                        logger.error(f"💥 MEDIA PROCESSOR: Document processing error for ID: {document_id}: {e}")
                        processing_data["z_transact_process"] = "error"
                else:
                    logger.error(f"❌ MEDIA PROCESSOR: No document ID found in upload result: {z_transact_result}")
            else:
                logger.error(f"❌ MEDIA PROCESSOR: Z-Transact upload failed - File: {upload_filename}")
                processing_data["z_transact_upload"] = "failed"

        except asyncio.TimeoutError:
            logger.error(f"Timeout during media processing for: {phone}")
            processing_data["status"] = "timeout"
        except Exception as e:
            logger.error(f"Media storage error: {e}")
            processing_data["status"] = "storage_failed"
            processing_data["error"] = str(e)

    async def stop_processing(self):
        """Stop background processing"""
        self.is_processing = False

# Global media processor instance
media_processor = MediaProcessor()