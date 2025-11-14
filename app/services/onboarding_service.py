"""
Onboarding Service
Handles new user registration with WhatsApp Flows for KYC collection
"""
import re
import logging
from datetime import datetime, date
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session
import hashlib

from app.models.user import User, UserStatus
from app.config import settings

logger = logging.getLogger(__name__)


class OnboardingService:
    """
    Manages user onboarding and KYC collection via WhatsApp Flows.
    """
    
    # South African ID number validation
    @staticmethod
    def validate_sa_id_number(id_number: str) -> Tuple[bool, Optional[date], Optional[str]]:
        """
        Validate South African ID number and extract date of birth.
        Format: YYMMDD GSSS CAZ
        Returns: (is_valid, date_of_birth, gender)
        """
        if not id_number or len(id_number) != 13:
            return False, None, None
        
        if not id_number.isdigit():
            return False, None, None
        
        try:
            # Extract date components
            year = int(id_number[0:2])
            month = int(id_number[2:4])
            day = int(id_number[4:6])
            
            # Determine century (assume < 25 is 2000s, else 1900s)
            current_year = datetime.now().year % 100
            if year <= current_year:
                year += 2000
            else:
                year += 1900
            
            # Validate date
            dob = date(year, month, day)
            
            # Extract gender (0-4999 = Female, 5000-9999 = Male)
            gender_code = int(id_number[6:10])
            gender = "Male" if gender_code >= 5000 else "Female"
            
            # Calculate age
            age = (datetime.now().date() - dob).days // 365
            
            # Must be 18+
            if age < 18:
                return False, dob, None
            
            return True, dob, gender
            
        except (ValueError, TypeError):
            return False, None, None
    
    # PIN REMOVED - Using WhatsApp chat lock instead
    
    @staticmethod
    def create_whatsapp_flow_json() -> Dict:
        """
        Create WhatsApp Flow JSON for KYC data collection.
        This is the interactive form that appears as a mini-app in WhatsApp.
        """
        return {
            "version": "3.0",
            "screens": [
                {
                    "id": "WELCOME",
                    "title": "Welcome to Cyrax! 🎉",
                    "data": {},
                    "layout": {
                        "type": "SingleColumnLayout",
                        "children": [
                            {
                                "type": "TextHeading",
                                "text": "Your AI Utility Assistant"
                            },
                            {
                                "type": "TextBody",
                                "text": "I help you:\n• Buy Airtime & Data\n• Pay Electricity Bills\n• Check Balances\n• View Transactions"
                            },
                            {
                                "type": "TextCaption",
                                "text": "Let's set up your account (takes 1 minute)"
                            },
                            {
                                "type": "Footer",
                                "label": "Continue",
                                "on-click-action": {
                                    "name": "navigate",
                                    "next": {"type": "screen", "name": "KYC_FORM"}
                                }
                            }
                        ]
                    }
                },
                {
                    "id": "KYC_FORM",
                    "title": "Account Setup",
                    "data": {
                        "first_name": {
                            "type": "string",
                            "__example__": "Thabo"
                        },
                        "last_name": {
                            "type": "string",
                            "__example__": "Mokoena"
                        },
                        "id_number": {
                            "type": "string",
                            "__example__": "9001011234567"
                        },
                        "pin": {
                            "type": "string",
                            "__example__": "1234"
                        },
                        "pin_confirm": {
                            "type": "string",
                            "__example__": "1234"
                        }
                    },
                    "layout": {
                        "type": "SingleColumnLayout",
                        "children": [
                            {
                                "type": "TextHeading",
                                "text": "Personal Details"
                            },
                            {
                                "type": "TextInput",
                                "name": "first_name",
                                "label": "First Name",
                                "input-type": "text",
                                "required": True,
                                "helper-text": "As per your ID"
                            },
                            {
                                "type": "TextInput",
                                "name": "last_name",
                                "label": "Last Name",
                                "input-type": "text",
                                "required": True
                            },
                            {
                                "type": "TextInput",
                                "name": "id_number",
                                "label": "SA ID Number",
                                "input-type": "number",
                                "required": True,
                                "helper-text": "13-digit South African ID"
                            },
                            {
                                "type": "TextHeading",
                                "text": "Security PIN"
                            },
                            {
                                "type": "TextCaption",
                                "text": "Create a 4-digit PIN to secure your transactions"
                            },
                            {
                                "type": "TextInput",
                                "name": "pin",
                                "label": "PIN (4 digits)",
                                "input-type": "passcode",
                                "required": True,
                                "min-chars": 4,
                                "max-chars": 4
                            },
                            {
                                "type": "TextInput",
                                "name": "pin_confirm",
                                "label": "Confirm PIN",
                                "input-type": "passcode",
                                "required": True,
                                "min-chars": 4,
                                "max-chars": 4
                            },
                            {
                                "type": "Footer",
                                "label": "Create Account",
                                "on-click-action": {
                                    "name": "complete",
                                    "payload": {
                                        "first_name": "${form.first_name}",
                                        "last_name": "${form.last_name}",
                                        "id_number": "${form.id_number}",
                                        "pin": "${form.pin}",
                                        "pin_confirm": "${form.pin_confirm}"
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        }
    
    @staticmethod
    async def process_flow_response(
        phone_number: str,
        flow_data: Dict,
        db: Session
    ) -> Tuple[bool, str, Optional[User]]:
        """
        Process registration data and create user account.
        NO PIN - using WhatsApp chat lock for security.
        Returns: (success, message, user)
        """
        try:
            # Extract data (NO PIN)
            first_name = flow_data.get("first_name", "").strip()
            last_name = flow_data.get("last_name", "").strip()
            id_number = flow_data.get("id_number", "").strip()
            
            # Validate required fields
            if not all([first_name, last_name, id_number]):
                return False, "❌ All fields are required. Please try again.", None
            
            # Validate name format
            if not re.match(r"^[a-zA-Z\s'-]+$", first_name) or not re.match(r"^[a-zA-Z\s'-]+$", last_name):
                return False, "❌ Names can only contain letters, spaces, hyphens, and apostrophes.", None
            
            # Validate SA ID number
            is_valid_id, dob, gender = OnboardingService.validate_sa_id_number(id_number)
            if not is_valid_id:
                if dob:  # Valid format but under 18
                    return False, "❌ You must be 18 or older to use Cyrax.", None
                else:
                    return False, "❌ Invalid South African ID number. Please check and try again.", None
            
            # Check if user already exists
            existing_user = db.query(User).filter(User.phone_number == phone_number).first()
            if existing_user and existing_user.is_fica_compliant:
                return False, "✅ You already have an account! Just send a message to get started.", existing_user
            
            # Check if ID number already used
            id_exists = db.query(User).filter(User.id_number == id_number).first()
            if id_exists:
                return False, "❌ This ID number is already registered. Contact support if this is an error.", None
            
            # Create or update user (NO PIN HASH)
            if existing_user:
                user = existing_user
                user.first_name = first_name
                user.last_name = last_name
                user.id_number = id_number
                user.date_of_birth = dob
                user.status = UserStatus.ACTIVE
                user.is_phone_verified = True
                user.is_id_verified = True
                user.is_fica_compliant = True
                user.verified_at = datetime.now()
            else:
                user = User(
                    phone_number=phone_number,
                    first_name=first_name,
                    last_name=last_name,
                    id_number=id_number,
                    date_of_birth=dob,
                    status=UserStatus.ACTIVE,
                    is_phone_verified=True,
                    is_id_verified=True,
                    is_fica_compliant=True,
                    verified_at=datetime.now(),
                    nationality="South African",
                    country="South Africa"
                )
                db.add(user)
            
            db.commit()
            db.refresh(user)
            
            logger.info(f"User onboarded successfully: {phone_number}")
            
            # Welcome message with WhatsApp security tip
            welcome_msg = f"""
🎉 Welcome to Cyrax, {first_name}!

✅ Your account is ready!

💡 What you can do:
• Buy Airtime - "Buy R50 MTN airtime"
• Buy Data - "Buy 1GB Vodacom data"
• Pay Electricity - "Pay R100 electricity for meter 12345"
• Check Balance - "What's my balance?"

🔒 Security Tip:
Lock this chat in WhatsApp to keep your account secure!
Settings > Chat Lock

Ready to get started? Just tell me what you need! 😊
            """.strip()
            
            return True, welcome_msg, user
            
        except Exception as e:
            logger.error(f"Onboarding error: {str(e)}")
            return False, "❌ Something went wrong. Please try again or contact support.", None
    
    @staticmethod
    def get_welcome_message_for_new_user() -> Dict:
        """
        Get welcome message with explanation of services for brand new users.
        """
        return {
            "type": "text",
            "text": """
👋 Hi! I'm Cyrax, your AI Utility Assistant!

🤖 What I Do:
• 📱 Buy Airtime (MTN, Vodacom, Cell C, Telkom)
• 📊 Buy Data Bundles
• ⚡ Pay Electricity Bills
• 💰 Check Your Balance
• 📋 View Transaction History

✨ Smart Features:
• Speak or type naturally
• Send voice notes - I understand!
• Take photos of meter numbers

🔐 Security:
All transactions are secured with WhatsApp's chat lock.
FICA compliant for your protection.

Ready to get started? Let's set up your account! (Takes just 1 minute)

Reply "YES" to continue or "INFO" to learn more.
            """.strip()
        }
    
    @staticmethod
    def should_onboard_user(user: Optional[User]) -> bool:
        """
        Check if user needs to complete onboarding.
        """
        if not user:
            return True
        
        # User needs onboarding if they haven't completed KYC
        if not user.is_fica_compliant:
            return True
        
        # User needs onboarding if missing critical fields (NO PIN CHECK)
        if not user.first_name or not user.last_name or not user.id_number:
            return True
        
        return False
    
    @staticmethod
    def get_onboarding_status_message(user: User) -> str:
        """
        Get message about what's missing for incomplete onboarding.
        """
        missing = []
        
        if not user.first_name or not user.last_name:
            missing.append("Full Name")
        
        if not user.id_number:
            missing.append("ID Number")
        
        if missing:
            return f"""
⚠️ Your account setup is incomplete!

Missing: {', '.join(missing)}

Please complete your registration to use Cyrax.

Reply "REGISTER" to continue setup.
            """.strip()
        
        return "✅ Account ready! What can I help you with?"


# Singleton instance
onboarding_service = OnboardingService()