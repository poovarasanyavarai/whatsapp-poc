import asyncio
from typing import Dict, Set
from datetime import datetime, timedelta
import hashlib
import json

class MessageDeduplicator:
    """Prevent duplicate webhook message processing"""

    def __init__(self, expiry_minutes: int = 60):
        self.processed_messages: Set[str] = set()
        self.message_timestamps: Dict[str, datetime] = {}
        self.expiry_minutes = expiry_minutes

    def _generate_message_hash(self, message_data: dict) -> str:
        """Generate unique hash for message deduplication"""
        key_fields = {
            "message_id": message_data.get("id"),
            "from_number": message_data.get("from"),
            "timestamp": message_data.get("timestamp"),
            "msg_type": message_data.get("type")
        }
        key_str = json.dumps(key_fields, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

    def is_duplicate(self, message_data: dict) -> bool:
        """Check if message has already been processed"""
        message_hash = self._generate_message_hash(message_data)

        if message_hash in self.processed_messages:
            return True

        # Clean expired messages
        self._cleanup_expired_messages()

        # Mark as processed
        self.processed_messages.add(message_hash)
        self.message_timestamps[message_hash] = datetime.now()
        return False

    def _cleanup_expired_messages(self):
        """Remove expired message hashes"""
        expiry_time = datetime.now() - timedelta(minutes=self.expiry_minutes)
        expired_hashes = [
            msg_hash for msg_hash, timestamp in self.message_timestamps.items()
            if timestamp < expiry_time
        ]

        for msg_hash in expired_hashes:
            self.processed_messages.discard(msg_hash)
            self.message_timestamps.pop(msg_hash, None)

# Global deduplicator instance
message_deduplicator = MessageDeduplicator()