"""
Conversation Model
Logs all WhatsApp conversations for AI training and support
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Conversation(Base):
    """
    Stores all WhatsApp messages and AI responses.
    Used for: AI training, customer support, compliance auditing.
    """
    __tablename__ = "conversations"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User Reference
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    
    # Message Details
    message_id = Column(String(100), unique=True, nullable=True)
    message_type = Column(String(20), nullable=False)
    direction = Column(String(10), nullable=False)
    
    # Content
    message_text = Column(Text, nullable=True)
    media_url = Column(String(500), nullable=True)
    media_mime_type = Column(String(50), nullable=True)
    
    # AI Processing
    ai_response = Column(Text, nullable=True)
    intent_detected = Column(String(50), nullable=True)
    entities_extracted = Column(JSONB, default={})
    confidence_score = Column(Float, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    
    # Context
    conversation_context = Column(JSONB, default={})
    session_id = Column(String(100), nullable=True, index=True)
    
    # Status
    is_processed = Column(Boolean, default=False)
    is_error = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    
    # Metadata
    conversation_metadata = Column(JSONB, default={})
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Conversation {self.phone_number} - {self.message_type}>"
