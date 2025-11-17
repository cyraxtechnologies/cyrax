"""
Response Validator - Catch AI Hallucinations
Prevents AI from making up actions or features
"""
import logging

logger = logging.getLogger(__name__)


def validate_ai_response(response: str) -> tuple[bool, str]:
    """
    Check if AI response contains hallucinations.
    
    Returns:
        (is_valid, corrected_response)
    """
    
    # Hallucination patterns - AI pretending to do actions
    hallucination_patterns = [
        "let me check",
        "i'll check",
        "i'm checking",
        "hold on",
        "please wait",
        "one moment",
        "i need to save",
        "i'll need to save",
        "i'll save",
        "let me save",
        "checking now",
        "checking your",
        "i'll verify",
        "verifying",
        "processing",
        "i'll process",
        "adding to"
    ]
    
    response_lower = response.lower()
    
    # Check for hallucinations
    for pattern in hallucination_patterns:
        if pattern in response_lower:
            logger.warning(f"Hallucination detected: '{pattern}' in response")
            
            # Return safe fallback
            return False, "I can help with that! What would you like to do?"
    
    # Check for invented features
    invented_features = [
        "add funds to your wallet",
        "top up your wallet",
        "deposit",
        "transfer money"
    ]
    
    for feature in invented_features:
        if feature in response_lower:
            logger.warning(f"Invented feature detected: '{feature}'")
            
            return False, "I can help with airtime, data, and electricity. What would you like?"
    
    return True, response


def sanitize_response(response: str) -> str:
    """
    Remove problematic phrases from AI response.
    """
    # Remove action phrases
    action_phrases = [
        "I'll ",
        "I will ",
        "Let me ",
        "I'm going to ",
    ]
    
    sanitized = response
    for phrase in action_phrases:
        sanitized = sanitized.replace(phrase, "")
    
    return sanitized.strip()