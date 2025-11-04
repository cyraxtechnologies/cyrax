"""
Transaction Service
Orchestrates all transaction logic for Cyrax
"""
from sqlalchemy.orm import Session
from typing import Dict, Optional, Tuple
import logging
from datetime import datetime, timedelta
import uuid
from decimal import Decimal

from app.models.user import User, UserStatus
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.services.payment_service import paystack_service
from app.config import settings

logger = logging.getLogger(__name__)


class TransactionService:
    """
    Handles all transaction processing logic for Cyrax.
    """
    
    @staticmethod
    async def send_money(
        db: Session,
        sender_id: str,
        recipient_phone: str,
        amount: float,
        description: Optional[str] = None,
        pin: Optional[str] = None
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """Send money from one user to another."""
        try:
            sender = db.query(User).filter(User.id == sender_id).first()
            if not sender:
                return False, "Sender not found", None
            
            can_transact, reason = sender.can_transact(amount)
            if not can_transact:
                return False, reason, None
            
            if sender.balance < amount:
                return False, f"Insufficient balance. Available: R{sender.balance:.2f}", None
            
            recipient = db.query(User).filter(User.phone_number == recipient_phone).first()
            if not recipient:
                recipient = User(
                    phone_number=recipient_phone,
                    status=UserStatus.PENDING_VERIFICATION
                )
                db.add(recipient)
                db.flush()
            
            fee = max(1.0, min(amount * 0.01, 50.0))
            total_amount = amount + fee
            
            transaction = Transaction(
                user_id=sender.id,
                type=TransactionType.SEND_MONEY,
                status=TransactionStatus.PROCESSING,
                amount=amount,
                currency="ZAR",
                sender_phone=sender.phone_number,
                recipient_phone=recipient_phone,
                recipient_name=recipient.full_name,
                transaction_fee=fee,
                total_amount=total_amount,
                description=description,
                payment_reference=f"CYR-{uuid.uuid4().hex[:12].upper()}",
                balance_before=sender.balance
            )
            db.add(transaction)
            
            try:
                sender.balance -= total_amount
                sender.daily_spent += amount
                sender.monthly_spent += amount
                
                recipient.balance += amount
                
                transaction.status = TransactionStatus.COMPLETED
                transaction.balance_after = sender.balance
                transaction.completed_at = datetime.utcnow()
                
                db.commit()
                
                logger.info(f"Transfer completed: {transaction.payment_reference}")
                return True, f"Successfully sent R{amount:.2f} to {recipient_phone}", transaction
                
            except Exception as e:
                db.rollback()
                transaction.status = TransactionStatus.FAILED
                transaction.failure_reason = str(e)
                transaction.failed_at = datetime.utcnow()
                db.commit()
                
                logger.error(f"Transfer failed: {str(e)}")
                return False, "Transaction failed. Please try again.", transaction
                
        except Exception as e:
            db.rollback()
            logger.error(f"Send money error: {str(e)}")
            return False, "An error occurred. Please try again.", None
    
    @staticmethod
    async def buy_airtime(
        db: Session,
        user_id: str,
        phone_number: str,
        amount: float,
        provider: str
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """Purchase airtime for a phone number."""
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False, "User not found", None
            
            can_transact, reason = user.can_transact(amount)
            if not can_transact:
                return False, reason, None
            
            fee = 1.0
            total_amount = amount + fee
            
            if user.balance < total_amount:
                return False, f"Insufficient balance. Available: R{user.balance:.2f}", None
            
            transaction = Transaction(
                user_id=user.id,
                type=TransactionType.AIRTIME_PURCHASE,
                status=TransactionStatus.PROCESSING,
                amount=amount,
                currency="ZAR",
                recipient_phone=phone_number,
                bill_provider=provider,
                transaction_fee=fee,
                total_amount=total_amount,
                description=f"{provider} airtime for {phone_number}",
                payment_reference=f"CYR-AIR-{uuid.uuid4().hex[:10].upper()}",
                balance_before=user.balance
            )
            db.add(transaction)
            db.flush()
            
            try:
                result = await paystack_service.buy_airtime(
                    phone_number=phone_number,
                    amount=amount,
                    provider=provider
                )
                
                user.balance -= total_amount
                user.daily_spent += amount
                user.monthly_spent += amount
                
                transaction.status = TransactionStatus.COMPLETED
                transaction.balance_after = user.balance
                transaction.gateway_reference = result.get("reference")
                transaction.gateway_response = result
                transaction.completed_at = datetime.utcnow()
                
                db.commit()
                
                logger.info(f"Airtime purchased: {transaction.payment_reference}")
                return True, f"R{amount:.2f} {provider} airtime sent to {phone_number}", transaction
                
            except Exception as e:
                db.rollback()
                transaction.status = TransactionStatus.FAILED
                transaction.failure_reason = str(e)
                transaction.failed_at = datetime.utcnow()
                db.commit()
                
                logger.error(f"Airtime purchase failed: {str(e)}")
                return False, "Airtime purchase failed. Please try again.", transaction
                
        except Exception as e:
            db.rollback()
            logger.error(f"Buy airtime error: {str(e)}")
            return False, "An error occurred. Please try again.", None
    
    @staticmethod
    async def buy_electricity(
        db: Session,
        user_id: str,
        meter_number: str,
        amount: float
    ) -> Tuple[bool, str, Optional[Transaction]]:
        """Purchase prepaid electricity."""
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False, "User not found", None
            
            can_transact, reason = user.can_transact(amount)
            if not can_transact:
                return False, reason, None
            
            fee = 2.50
            total_amount = amount + fee
            
            if user.balance < total_amount:
                return False, f"Insufficient balance. Available: R{user.balance:.2f}", None
            
            transaction = Transaction(
                user_id=user.id,
                type=TransactionType.ELECTRICITY_PURCHASE,
                status=TransactionStatus.PROCESSING,
                amount=amount,
                currency="ZAR",
                bill_provider="Eskom",
                bill_account_number=meter_number,
                transaction_fee=fee,
                total_amount=total_amount,
                description=f"Prepaid electricity for meter {meter_number}",
                payment_reference=f"CYR-ELEC-{uuid.uuid4().hex[:10].upper()}",
                balance_before=user.balance
            )
            db.add(transaction)
            db.flush()
            
            try:
                user.balance -= total_amount
                user.daily_spent += amount
                user.monthly_spent += amount
                
                transaction.status = TransactionStatus.COMPLETED
                transaction.balance_after = user.balance
                transaction.completed_at = datetime.utcnow()
                
                transaction.transaction_metadata = {
                    "token": "1234-5678-9012-3456",
                    "units": amount / 2.5,
                    "meter_number": meter_number
                }
                
                db.commit()
                
                logger.info(f"Electricity purchased: {transaction.payment_reference}")
                return True, f"R{amount:.2f} electricity purchased. Token: 1234-5678-9012-3456", transaction
                
            except Exception as e:
                db.rollback()
                transaction.status = TransactionStatus.FAILED
                transaction.failure_reason = str(e)
                transaction.failed_at = datetime.utcnow()
                db.commit()
                
                logger.error(f"Electricity purchase failed: {str(e)}")
                return False, "Electricity purchase failed. Please try again.", transaction
                
        except Exception as e:
            db.rollback()
            logger.error(f"Buy electricity error: {str(e)}")
            return False, "An error occurred. Please try again.", None
    
    @staticmethod
    def get_user_balance(db: Session, user_id: str) -> Optional[Dict]:
        """Get user's current balance and limits."""
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None
            
            now = datetime.utcnow()
            if user.last_daily_reset.date() < now.date():
                user.daily_spent = 0.0
                user.last_daily_reset = now
                db.commit()
            
            if user.last_monthly_reset.month < now.month or user.last_monthly_reset.year < now.year:
                user.monthly_spent = 0.0
                user.last_monthly_reset = now
                db.commit()
            
            return {
                "balance": user.balance,
                "daily_limit_remaining": user.available_daily_limit,
                "monthly_limit_remaining": user.available_monthly_limit,
                "daily_spent": user.daily_spent,
                "monthly_spent": user.monthly_spent
            }
            
        except Exception as e:
            logger.error(f"Get balance error: {str(e)}")
            return None
    
    @staticmethod
    def get_transaction_history(
        db: Session,
        user_id: str,
        limit: int = 10
    ) -> list:
        """Get user's recent transactions."""
        try:
            transactions = db.query(Transaction).filter(
                Transaction.user_id == user_id
            ).order_by(
                Transaction.created_at.desc()
            ).limit(limit).all()
            
            return [t.to_dict() for t in transactions]
            
        except Exception as e:
            logger.error(f"Get history error: {str(e)}")
            return []


# Singleton instance
transaction_service = TransactionService()
