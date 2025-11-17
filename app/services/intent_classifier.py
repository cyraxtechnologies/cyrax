"""
Intent Classifier - Rule-Based (No AI Guessing)
Deterministic intent detection to prevent hallucinations
"""
from typing import Dict, Optional
from sqlalchemy.orm import Session
import re
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def fuzzy_match(text: str, target: str, threshold: float = 0.75) -> bool:
    """Check if text fuzzy matches target (handles typos)"""
    ratio = SequenceMatcher(None, text.lower(), target.lower()).ratio()
    return ratio >= threshold


def classify_intent(message: str, user_id: str, db: Session) -> Dict:
    """
    Rule-based intent classification.
    Returns structured intent with handler function name.
    
    Returns:
        {
            "intent": str,
            "entities": dict,
            "handler": str | None,
            "use_ai": bool,
            "confidence": float,
            "suggested_intent": str (if typo detected)
        }
    """
    msg = message.lower().strip()
    
    # Check for typos in common commands
    typo_suggestions = {
        "show beneficiaries": ["show beneficiar", "beneficiries", "beneficireis", "beneficiries"],
        "buy airtime": ["buy airtime", "airtime", "buy air time"],
        "buy data": ["buy data", "data bundle"],
        "check balance": ["balance", "my balance", "wallet"],
    }
    
    for correct_command, variations in typo_suggestions.items():
        for variation in variations:
            if fuzzy_match(msg, variation, 0.65):
                # Found potential typo - return with suggestion
                return {
                    "intent": "typo_detected",
                    "entities": {},
                    "handler": "handle_typo_confirmation",
                    "use_ai": False,
                    "confidence": 0.8,
                    "suggested_intent": correct_command,
                    "original_message": message
                }
    
    # Pattern 1: Save beneficiary
    if msg.startswith("save ") or "save beneficiary" in msg or "save beneficiar" in msg:
        return {
            "intent": "save_beneficiary",
            "entities": {},
            "handler": "handle_save_beneficiary",
            "use_ai": False,
            "confidence": 0.95
        }
    
    # Pattern 2: Show/list beneficiaries (with typo tolerance)
    show_keywords = ["show beneficiar", "list beneficiar", "my beneficiar", "saved contacts"]
    if any(keyword in msg for keyword in show_keywords) or fuzzy_match(msg, "show beneficiaries", 0.7):
        return {
            "intent": "show_beneficiaries",
            "entities": {},
            "handler": "handle_show_beneficiaries",
            "use_ai": False,
            "confidence": 0.95
        }
    
    # Pattern 3: Delete beneficiary
    if msg.startswith("delete ") or msg.startswith("remove "):
        return {
            "intent": "delete_beneficiary",
            "entities": {},
            "handler": "handle_delete_beneficiary",
            "use_ai": False,
            "confidence": 0.9
        }
    
    # Pattern 4: Check balance
    if any(word in msg for word in ["balance", "wallet", "how much money"]):
        return {
            "intent": "check_balance",
            "entities": {},
            "handler": "handle_check_balance",
            "use_ai": False,
            "confidence": 0.95
        }
    
    # Pattern 5: Account details
    if any(phrase in msg for phrase in ["account details", "my details", "my account", "account info", "show my info"]):
        return {
            "intent": "account_details",
            "entities": {},
            "handler": "handle_account_details",
            "use_ai": False,
            "confidence": 0.95
        }
    
    # Pattern 6: Transaction with beneficiary reference
    # "recharge mom", "buy airtime for thabo", "electricity for home"
    if any(word in msg for word in ["recharge", "buy", "pay", "send"]):
        # Check if any saved beneficiary is mentioned
        from app.services.beneficiary_service import beneficiary_service
        
        beneficiaries = beneficiary_service.get_beneficiaries(user_id, None, db)
        mentioned_beneficiary = None
        
        for beneficiary in beneficiaries:
            if beneficiary.nickname.lower() in msg:
                mentioned_beneficiary = beneficiary
                break
        
        if mentioned_beneficiary:
            # Extract amount
            amount = extract_amount(msg)
            
            return {
                "intent": "beneficiary_transaction",
                "entities": {
                    "beneficiary": mentioned_beneficiary,
                    "amount": amount
                },
                "handler": "handle_beneficiary_transaction",
                "use_ai": False if amount else True,  # Use AI only if amount missing
                "confidence": 0.9
            }
    
    # Pattern 7: Buy airtime (no beneficiary)
    if any(word in msg for word in ["airtime", "recharge", "topup", "top up"]):
        phone = extract_phone(msg)
        amount = extract_amount(msg)
        
        return {
            "intent": "buy_airtime",
            "entities": {
                "phone": phone,
                "amount": amount
            },
            "handler": "handle_buy_airtime" if (phone and amount) else None,
            "use_ai": not (phone and amount),  # Use AI if incomplete
            "confidence": 0.85
        }
    
    # Pattern 7: Buy data
    if any(word in msg for word in ["data", "bundle", "gigs", "gb", "mb"]):
        phone = extract_phone(msg)
        amount = extract_amount(msg)
        
        return {
            "intent": "buy_data",
            "entities": {
                "phone": phone,
                "amount": amount
            },
            "handler": None,  # Not implemented yet
            "use_ai": True,
            "confidence": 0.85
        }
    
    # Pattern 8: Electricity (no beneficiary)
    if any(word in msg for word in ["electricity", "power", "token", "eskom", "meter"]):
        meter = extract_meter_number(msg)
        amount = extract_amount(msg)
        
        return {
            "intent": "buy_electricity",
            "entities": {
                "meter_number": meter,
                "amount": amount
            },
            "handler": None,  # Not implemented yet
            "use_ai": True,
            "confidence": 0.85
        }
    
    # Pattern 9: Greetings
    if any(word in msg for word in ["hi", "hello", "hey", "start", "menu"]):
        return {
            "intent": "greeting",
            "entities": {},
            "handler": None,
            "use_ai": True,  # AI gives friendly greeting
            "confidence": 0.9
        }
    
    # Pattern 10: Help
    if any(word in msg for word in ["help", "what can", "commands", "options"]):
        return {
            "intent": "help",
            "entities": {},
            "handler": "send_menu",
            "use_ai": False,
            "confidence": 0.95
        }
    
    # Default: Unclear - use AI
    return {
        "intent": "unclear",
        "entities": {},
        "handler": None,
        "use_ai": True,
        "confidence": 0.5
    }


def extract_amount(text: str) -> Optional[float]:
    """Extract monetary amount from text."""
    patterns = [
        r'r\s*(\d+(?:\.\d{2})?)',  # R50 or R 50
        r'(\d+(?:\.\d{2})?)\s*rand',  # 50 rand
        r'\b(\d+(?:\.\d{2})?)\b'  # Just numbers
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            try:
                return float(match.group(1))
            except:
                continue
    return None


def extract_phone(text: str) -> Optional[str]:
    """Extract South African phone number from text."""
    patterns = [
        r'(\+27\d{9})',  # +27821234567
        r'(0\d{9})',  # 0821234567
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            phone = match.group(1).replace(' ', '')
            return phone
    return None


def extract_meter_number(text: str) -> Optional[str]:
    """Extract electricity meter number from text."""
    pattern = r'\b(\d{11})\b'
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    return None


def extract_network(text: str) -> Optional[str]:
    """Extract mobile network from text."""
    text_lower = text.lower()
    networks = {
        "mtn": ["mtn"],
        "vodacom": ["vodacom", "voda"],
        "cell c": ["cell c", "cellc", "cell-c"],
        "telkom": ["telkom"]
    }
    
    for network, keywords in networks.items():
        if any(keyword in text_lower for keyword in keywords):
            return network
    return None