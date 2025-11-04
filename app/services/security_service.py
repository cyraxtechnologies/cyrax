"""
Security Service
Handles PIN hashing, verification, and fraud detection for Cyrax
"""
from passlib.context import CryptContext
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging
from typing import Optional, Tuple
import re

from app.models.user import User
from app.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class SecurityService:
    """
    Handles all security-related operations for Cyrax.
    """
    
    @staticmethod
    def hash_pin(pin: str) -> str:
        """Hash a PIN securely using bcrypt."""
        pin_str = str(pin).strip()
        return pwd_context.hash(pin_str)
    
    @staticmethod
    def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
        """Verify a PIN against its hash."""
        try:
            plain_pin = str(plain_pin).strip()
            return pwd_context.verify(plain_pin, hashed_pin)
        except Exception as e:
            logger.error(f"PIN verification error: {str(e)}")
            return False
    
    @staticmethod
    def validate_pin_format(pin: str) -> Tuple[bool, str]:
        """Validate PIN format."""
        pin = str(pin).strip()
        
        if not pin:
            return False, "PIN is required"
        
        if not pin.isdigit():
            return False, "PIN must contain only numbers"
        
        if len(pin) < 4 or len(pin) > 6:
            return False, "PIN must be 4-6 digits"
        
        weak_pins = ["0000", "1111", "2222", "3333", "4444", "5555", 
                     "6666", "7777", "8888", "9999", "1234", "4321"]
        if pin in weak_pins:
            return False, "PIN is too weak. Choose a stronger PIN"
        
        return True, ""
    
    @staticmethod
    async def verify_user_pin(
        db: Session,
        user_id: str,
        pin: str
    ) -> Tuple[bool, str]:
        """Verify user's transaction PIN with rate limiting."""
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False, "User not found"
            
            if user.pin_locked_until and user.pin_locked_until > datetime.utcnow():
                minutes_left = int((user.pin_locked_until - datetime.utcnow()).total_seconds() / 60)
                return False, f"PIN locked. Try again in {minutes_left} minutes"
            
            if not user.pin_hash:
                return False, "Please set up your PIN first. Reply 'SET PIN' to create one"
            
            if SecurityService.verify_pin(pin, user.pin_hash):
                user.pin_attempts = 0
                user.pin_locked_until = None
                db.commit()
                return True, "PIN verified"
            else:
                user.pin_attempts += 1
                
                if user.pin_attempts >= 3:
                    user.pin_locked_until = datetime.utcnow() + timedelta(minutes=30)
                    db.commit()
                    return False, "Too many failed attempts. PIN locked for 30 minutes"
                
                db.commit()
                remaining = 3 - user.pin_attempts
                return False, f"Incorrect PIN. {remaining} attempts remaining"
                
        except Exception as e:
            logger.error(f"PIN verification error: {str(e)}")
            return False, "PIN verification failed"
    
    @staticmethod
    async def set_user_pin(
        db: Session,
        user_id: str,
        new_pin: str
    ) -> Tuple[bool, str]:
        """Set or update user's transaction PIN."""
        try:
            # Clean the PIN
            new_pin = str(new_pin).strip()
            
            # Validate format
            is_valid, error_msg = SecurityService.validate_pin_format(new_pin)
            if not is_valid:
                return False, error_msg
            
            # Get user
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False, "User not found"
            
            # Hash and save PIN
            user.pin_hash = pwd_context.hash(new_pin)
            user.pin_attempts = 0
            user.pin_locked_until = None
            db.commit()
            
            logger.info(f"PIN set successfully for user {user_id}")
            return True, "PIN set successfully! You can now make transactions"
            
        except Exception as e:
            db.rollback()
            logger.error(f"Set PIN error: {str(e)}")
            return False, f"Failed to set PIN: {str(e)}"
    
    @staticmethod
    def validate_phone_number(phone: str) -> Tuple[bool, str]:
        """Validate South African phone number."""
        cleaned = re.sub(r'\D', '', phone)
        
        if len(cleaned) == 10 and cleaned.startswith('0'):
            return True, cleaned
        elif len(cleaned) == 11 and cleaned.startswith('27'):
            return True, cleaned
        elif len(cleaned) == 9:
            return True, f"27{cleaned}"
        
        return False, ""
    
    @staticmethod
    def detect_fraud(
        db: Session,
        user_id: str,
        amount: float,
        recipient_phone: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Simple fraud detection rules."""
        from app.models.transaction import Transaction
        
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return True, "User not found"
            
            if user.created_at > datetime.utcnow() - timedelta(days=7):
                if amount > 1000:
                    return True, "High amount for new account. Please verify your identity first"
            
            recent_transactions = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.created_at > datetime.utcnow() - timedelta(minutes=5)
            ).count()
            
            if recent_transactions >= 5:
                return True, "Too many transactions in short time. Please wait a few minutes"
            
            if recipient_phone:
                recent_to_same = db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.recipient_phone == recipient_phone,
                    Transaction.created_at > datetime.utcnow() - timedelta(minutes=10)
                ).count()
                
                if recent_to_same >= 3:
                    return True, "Multiple transactions to same recipient. Please contact support"
            
            if amount in [100, 200, 500, 1000, 2000, 5000]:
                recent_round = db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.amount.in_([100, 200, 500, 1000, 2000, 5000]),
                    Transaction.created_at > datetime.utcnow() - timedelta(hours=1)
                ).count()
                
                if recent_round >= 3:
                    return True, "Suspicious transaction pattern detected. Please verify via support"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"Fraud detection error: {str(e)}")
            return False, ""
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Sanitize user input to prevent injection attacks."""
        dangerous_patterns = [
            r"(?i)(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC|EXECUTE|SCRIPT)",
            r"[<>]",
            r"javascript:",
        ]
        
        sanitized = text
        for pattern in dangerous_patterns:
            sanitized = re.sub(pattern, "", sanitized)
        
        return sanitized.strip()


# Singleton instance
security_service = SecurityService()