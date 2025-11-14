"""
Beneficiary Model
Save frequently used phone numbers and meter numbers
"""
from sqlalchemy import Column, String, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from datetime import datetime

from app.database import Base


class BeneficiaryType(str, enum.Enum):
    """Type of beneficiary"""
    PHONE = "phone"  # For airtime/data
    METER = "meter"  # For electricity
    ACCOUNT = "account"  # For bills


class Beneficiary(Base):
    """Store user's saved beneficiaries"""
    __tablename__ = "beneficiaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Beneficiary details
    nickname = Column(String(100), nullable=False)  # "Mom", "Thabo", "Home meter"
    beneficiary_type = Column(SQLEnum(BeneficiaryType), nullable=False)
    value = Column(String(255), nullable=False)  # Phone number or meter number
    network = Column(String(50), nullable=True)  # MTN, Vodacom, etc (for phones)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="beneficiaries")
    
    def __repr__(self):
        return f"<Beneficiary {self.nickname}: {self.value}>"