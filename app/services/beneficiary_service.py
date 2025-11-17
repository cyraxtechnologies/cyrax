"""
Beneficiary Service - Manage saved contacts and utility accounts
"""
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session
from app.models.beneficiary import Beneficiary, BeneficiaryType
import logging

logger = logging.getLogger(__name__)


class BeneficiaryService:
    """Service for managing user beneficiaries"""
    
    def save_beneficiary(
        self,
        user_id: str,
        nickname: str,
        value: str,
        beneficiary_type: BeneficiaryType,
        network: Optional[str],
        db: Session
    ) -> Tuple[bool, str, Optional[Beneficiary]]:
        """
        Save a new beneficiary.
        
        Returns:
            (success, message, beneficiary)
        """
        try:
            # Check if nickname already exists
            existing = db.query(Beneficiary).filter(
                Beneficiary.user_id == user_id,
                Beneficiary.nickname.ilike(nickname)
            ).first()
            
            if existing:
                return False, f"❌ '{nickname}' already exists. Use a different name or delete the old one first.", None
            
            # Create beneficiary
            beneficiary = Beneficiary(
                user_id=user_id,
                nickname=nickname,
                value=value,
                beneficiary_type=beneficiary_type,
                network=network
            )
            
            db.add(beneficiary)
            db.commit()
            db.refresh(beneficiary)
            
            # Format success message based on type
            icon = self._get_type_icon(beneficiary_type)
            return True, f"✅ Saved '{nickname}' {icon}\n{value}", beneficiary
            
        except Exception as e:
            logger.error(f"Error saving beneficiary: {str(e)}")
            db.rollback()
            return False, "❌ Failed to save beneficiary. Please try again.", None
    
    def get_beneficiaries(
        self,
        user_id: str,
        beneficiary_type: Optional[BeneficiaryType],
        db: Session
    ) -> List[Beneficiary]:
        """Get all beneficiaries for a user, optionally filtered by type"""
        query = db.query(Beneficiary).filter(Beneficiary.user_id == user_id)
        
        if beneficiary_type:
            query = query.filter(Beneficiary.beneficiary_type == beneficiary_type)
        
        return query.order_by(Beneficiary.created_at.desc()).all()
    
    def find_beneficiary(
        self,
        user_id: str,
        nickname: str,
        db: Session
    ) -> Optional[Beneficiary]:
        """Find a beneficiary by nickname (case-insensitive)"""
        return db.query(Beneficiary).filter(
            Beneficiary.user_id == user_id,
            Beneficiary.nickname.ilike(nickname)
        ).first()
    
    def delete_beneficiary(
        self,
        user_id: str,
        nickname: str,
        db: Session
    ) -> Tuple[bool, str]:
        """Delete a beneficiary by nickname"""
        try:
            beneficiary = self.find_beneficiary(user_id, nickname, db)
            
            if not beneficiary:
                return False, f"❌ '{nickname}' not found in your beneficiaries."
            
            db.delete(beneficiary)
            db.commit()
            
            return True, f"✅ Deleted '{nickname}'"
            
        except Exception as e:
            logger.error(f"Error deleting beneficiary: {str(e)}")
            db.rollback()
            return False, "❌ Failed to delete beneficiary. Please try again."
    
    def format_beneficiary_list(self, beneficiaries: List[Beneficiary]) -> str:
        """Format beneficiaries for display"""
        if not beneficiaries:
            return "📋 No saved beneficiaries yet.\n\nSave one with:\nsave [name] [number]"
        
        message = "💾 *Your Beneficiaries:*\n\n"
        
        for b in beneficiaries:
            icon = self._get_type_icon(b.beneficiary_type)
            message += f"{icon} *{b.nickname}*\n"
            message += f"   {b.value}\n"
            if b.network:
                message += f"   Network: {b.network}\n"
            message += "\n"
        
        return message.strip()
    
    def _get_type_icon(self, beneficiary_type: BeneficiaryType) -> str:
        """Get emoji icon for beneficiary type"""
        icons = {
            BeneficiaryType.PHONE: "📱",
            BeneficiaryType.METER: "⚡",
            BeneficiaryType.WATER: "💧",
            BeneficiaryType.INTERNET: "🌐",
            BeneficiaryType.TV: "📺",
            BeneficiaryType.MUNICIPAL: "🏛️",
            BeneficiaryType.OTHER: "💳"
        }
        return icons.get(beneficiary_type, "💳")


# Singleton instance
beneficiary_service = BeneficiaryService()