"""
Transaction Model
Stores all financial transactions with full audit trail
"""
from sqlalchemy import Column, String, DateTime, Float, Integer, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.database import Base


class TransactionStatus(str, enum.Enum):
    """Transaction processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class TransactionType(str, enum.Enum):
    """Types of transactions"""
    SEND_MONEY = "send_money"
    RECEIVE_MONEY = "receive_money"
    BILL_PAYMENT = "bill_payment"
    AIRTIME_PURCHASE = "airtime_purchase"
    DATA_PURCHASE = "data_purchase"
    ELECTRICITY_PURCHASE = "electricity_purchase"
    WITHDRAWAL = "withdrawal"
    DEPOSIT = "deposit"
    REFUND = "refund"


class Transaction(Base):
    """
    Transaction model for all financial operations.
    Maintains complete audit trail for compliance.
    """
    __tablename__ = "transactions"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User Reference
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Transaction Details
    type = Column(SQLEnum(TransactionType), nullable=False, index=True)
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="ZAR")
    
    # Parties Involved
    sender_phone = Column(String(20), nullable=True)
    recipient_phone = Column(String(20), nullable=True)
    recipient_name = Column(String(255), nullable=True)
    recipient_bank = Column(String(100), nullable=True)
    recipient_account = Column(String(50), nullable=True)
    
    # Bill Payment Details
    bill_provider = Column(String(100), nullable=True)
    bill_account_number = Column(String(100), nullable=True)
    bill_reference = Column(String(100), nullable=True)
    
    # Payment Gateway Details
    payment_reference = Column(String(100), unique=True, nullable=True, index=True)
    gateway_reference = Column(String(100), nullable=True)
    gateway_response = Column(JSONB, default={})
    
    # Fees and Charges
    transaction_fee = Column(Float, default=0.0)
    gateway_fee = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    
    # Balance Tracking
    balance_before = Column(Float, nullable=True)
    balance_after = Column(Float, nullable=True)
    
    # Description and Notes
    description = Column(Text, nullable=True)
    user_note = Column(Text, nullable=True)
    admin_note = Column(Text, nullable=True)
    
    # AI Context
    original_message = Column(Text, nullable=True)
    intent_detected = Column(String(50), nullable=True)
    
    # Failure Handling
    failure_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Metadata
    transaction_metadata = Column(JSONB, default={})
    ip_address = Column(String(50), nullable=True)
    device_info = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Transaction {self.id} - {self.type} - {self.status}>"
    
    @property
    def is_successful(self) -> bool:
        """Check if transaction completed successfully"""
        return self.status == TransactionStatus.COMPLETED
    
    @property
    def is_pending(self) -> bool:
        """Check if transaction is still pending"""
        return self.status in [TransactionStatus.PENDING, TransactionStatus.PROCESSING]
    
    def to_dict(self) -> dict:
        """Convert transaction to dictionary for API responses"""
        return {
            "id": str(self.id),
            "type": self.type.value,
            "status": self.status.value,
            "amount": self.amount,
            "total_amount": self.total_amount,
            "currency": self.currency,
            "description": self.description,
            "recipient_name": self.recipient_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
