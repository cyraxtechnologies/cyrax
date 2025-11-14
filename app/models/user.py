"""
User Model
Stores all user information including KYC data for FICA compliance
"""
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Boolean, DateTime, Float, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import enum

from app.database import Base


class UserStatus(str, enum.Enum):
    """User account status"""
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


class User(Base):
    """
    User model for storing customer information.
    Includes FICA compliance fields (KYC data).
    """
    __tablename__ = "users"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Contact Information
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True)
    whatsapp_name = Column(String(255), nullable=True)
    
    # Personal Information (FICA Requirements)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    id_number = Column(String(20), unique=True, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    nationality = Column(String(50), nullable=True)
    
    # Address Information (FICA - Proof of Residence)
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    province = Column(String(100), nullable=True)
    postal_code = Column(String(10), nullable=True)
    country = Column(String(50), default="South Africa")
    
    # Account Information
    account_number = Column(String(50), unique=True, nullable=True)
    balance = Column(Float, default=0.0, nullable=False)
    status = Column(SQLEnum(UserStatus), default=UserStatus.PENDING_VERIFICATION)
    
    # Security
    pin_hash = Column(String(255), nullable=True)
    pin_attempts = Column(Integer, default=0)
    pin_locked_until = Column(DateTime, nullable=True)
    
    # Verification Status (FICA)
    is_phone_verified = Column(Boolean, default=False)
    is_email_verified = Column(Boolean, default=False)
    is_id_verified = Column(Boolean, default=False)
    is_address_verified = Column(Boolean, default=False)
    is_fica_compliant = Column(Boolean, default=False)
    
    # KYC Documents
    id_document_url = Column(String(500), nullable=True)
    proof_of_residence_url = Column(String(500), nullable=True)
    selfie_url = Column(String(500), nullable=True)
    
    # Transaction Limits
    daily_limit = Column(Float, default=25000.0)
    monthly_limit = Column(Float, default=100000.0)
    daily_spent = Column(Float, default=0.0)
    monthly_spent = Column(Float, default=0.0)
    last_daily_reset = Column(DateTime, default=func.now())
    last_monthly_reset = Column(DateTime, default=func.now())
    
    # Preferences
    preferred_language = Column(String(10), default="en")
    notification_enabled = Column(Boolean, default=True)
    marketing_consent = Column(Boolean, default=False)
    
    # Metadata
    user_metadata = Column(JSONB, default={})
    referral_code = Column(String(20), unique=True, nullable=True)
    referred_by = Column(UUID(as_uuid=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_active_at = Column(DateTime, default=func.now())
    verified_at = Column(DateTime, nullable=True)

    # Beneficiaries
    beneficiaries = relationship("Beneficiary", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.phone_number} - {self.status}>"
    
    @property
    def full_name(self):
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.whatsapp_name or self.phone_number
    
    @property
    def available_daily_limit(self):
        """Calculate remaining daily transaction limit"""
        return max(0, self.daily_limit - self.daily_spent)
    
    @property
    def available_monthly_limit(self):
        """Calculate remaining monthly transaction limit"""
        return max(0, self.monthly_limit - self.monthly_spent)
    
    def can_transact(self, amount: float) -> tuple[bool, str]:
        """
        Check if user can make a transaction of given amount.
        Returns (can_transact, reason)
        """
        if self.status != UserStatus.ACTIVE:
            return False, f"Account is {self.status}"
        
        if not self.is_fica_compliant:
            return False, "FICA verification incomplete"
        
        if amount > self.available_daily_limit:
            return False, f"Daily limit exceeded. Available: R{self.available_daily_limit:.2f}"
        
        if amount > self.available_monthly_limit:
            return False, f"Monthly limit exceeded. Available: R{self.available_monthly_limit:.2f}"
        
        return True, "OK"
