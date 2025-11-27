from fastapi import APIRouter, HTTPException
from typing import Dict, List
from datetime import datetime, timedelta
import json
from src.config import logger
from src.services.media_processor import media_processor

router = APIRouter()

@router.get("/status")
async def get_system_status():
    """Get current system status including media processing queue"""
    try:
        queue_size = media_processor.processing_queue.qsize()
        is_processing = media_processor.is_processing

        # Get recent logs (last 100 lines)
        recent_logs = []
        # In production, you'd implement proper log aggregation

        status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "media_processing": {
                "queue_size": queue_size,
                "is_processing": is_processing,
                "queue_status": "active" if is_processing else "idle"
            },
            "webhook": {
                "status": "active",
                "processing_mode": "async_media"
            }
        }

        return status
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get system status")

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "webhook": "active",
            "media_processor": "active" if media_processor.is_processing else "idle"
        }
    }