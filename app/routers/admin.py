"""
Admin Router
Simple admin endpoints for monitoring Cyrax
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict
import logging

from app.database import get_db
from app.models.user import User, UserStatus
from app.models.transaction import Transaction, TransactionStatus
from app.models.conversation import Conversation

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get Cyrax platform statistics."""
    try:
        total_users = db.query(func.count(User.id)).scalar()
        active_users = db.query(func.count(User.id)).filter(
            User.status == UserStatus.ACTIVE
        ).scalar()
        verified_users = db.query(func.count(User.id)).filter(
            User.is_fica_compliant == True
        ).scalar()
        
        total_transactions = db.query(func.count(Transaction.id)).scalar()
        completed_transactions = db.query(func.count(Transaction.id)).filter(
            Transaction.status == TransactionStatus.COMPLETED
        ).scalar()
        failed_transactions = db.query(func.count(Transaction.id)).filter(
            Transaction.status == TransactionStatus.FAILED
        ).scalar()
        
        total_volume = db.query(func.sum(Transaction.amount)).filter(
            Transaction.status == TransactionStatus.COMPLETED
        ).scalar() or 0.0
        
        total_messages = db.query(func.count(Conversation.id)).scalar()
        
        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "verified": verified_users,
                "verification_rate": f"{(verified_users/total_users*100) if total_users > 0 else 0:.1f}%"
            },
            "transactions": {
                "total": total_transactions,
                "completed": completed_transactions,
                "failed": failed_transactions,
                "success_rate": f"{(completed_transactions/total_transactions*100) if total_transactions > 0 else 0:.1f}%",
                "total_volume": f"R{total_volume:,.2f}"
            },
            "conversations": {
                "total_messages": total_messages
            }
        }
        
    except Exception as e:
        logger.error(f"Stats error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users")
async def list_users(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """List users with pagination."""
    try:
        users = db.query(User).offset(skip).limit(limit).all()
        
        return {
            "users": [
                {
                    "id": str(user.id),
                    "phone": user.phone_number,
                    "name": user.full_name,
                    "balance": user.balance,
                    "status": user.status.value,
                    "fica_compliant": user.is_fica_compliant,
                    "created_at": user.created_at.isoformat()
                }
                for user in users
            ],
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"List users error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transactions/recent")
async def recent_transactions(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """Get recent transactions."""
    try:
        transactions = db.query(Transaction).order_by(
            Transaction.created_at.desc()
        ).limit(limit).all()
        
        return {
            "transactions": [txn.to_dict() for txn in transactions]
        }
        
    except Exception as e:
        logger.error(f"Recent transactions error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-ai")
async def test_ai():
    """Test OpenAI connection."""
    try:
        from app.services.ai_service import AIService
        
        result = await AIService.process_message(
            message="Send R100 to my friend John",
            user_context={
                "name": "Test User",
                "phone": "0821234567",
                "balance": 500.0,
                "daily_limit_remaining": 5000.0,
                "is_fica_compliant": True
            }
        )
        
        return {
            "status": "success",
            "openai_working": True,
            "ai_response": result["response"],
            "intent": result["intent"],
            "confidence": result["confidence"]
        }
    except Exception as e:
        return {
            "status": "error",
            "openai_working": False,
            "error": str(e)
        }