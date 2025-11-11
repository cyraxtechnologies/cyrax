"""
Enhanced AI Service with Voice & Image Processing
Handles AI interactions, voice transcription, and image OCR
"""
from typing import Dict, List, Optional
import re
import logging
import base64
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class AIService:
    """
    Enhanced AI service for processing messages, voice notes, and images.
    """
    
    # Updated system prompt for utility bill assistant focus
    SYSTEM_PROMPT = """You are Cyrax, a friendly AI utility bill assistant for South African users on WhatsApp. 

Your role:
- Help users buy airtime and data bundles
- Pay electricity bills (prepaid tokens)
- Check account balance and transaction history
- Understand South African slang, accents, and languages (English, Afrikaans, Zulu, Xhosa)
- Be conversational, warm, and helpful

Key capabilities:
1. Buy airtime for MTN, Vodacom, Cell C, Telkom (R5 - R1000)
2. Buy data bundles for all networks
3. Pay for prepaid electricity (Eskom and municipalities)
4. Check wallet balance
5. View transaction history

Important rules:
- ALWAYS confirm transaction details before processing
- Ask for PIN when processing payments
- Explain any fees upfront (typically 2-5% service fee)
- Be security-conscious

South African context:
- Currency is ZAR (Rand), use R symbol
- Common airtime amounts: R10, R20, R50, R100, R500
- Mobile providers: MTN (083/084), Vodacom (082/072), Cell C (084), Telkom (081)
- Electricity: prepaid tokens with 20-digit codes

NOTE: Money transfers will be available soon once we obtain our banking license!

Respond naturally and conversationally. Keep messages concise for WhatsApp."""

    @staticmethod
    async def process_message(
        message: str,
        user_context: Dict,
        conversation_history: List[Dict] = None
    ) -> Dict:
        """
        Process a user message and return intent, entities, and response.
        """
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            # Build conversation context
            messages = [
                {"role": "system", "content": AIService.SYSTEM_PROMPT}
            ]
            
            # Add user context
            context_msg = f"""
            User Information:
            - Name: {user_context.get('name', 'User')}
            - Wallet Balance: R{user_context.get('balance', 0):.2f}
            - Phone: {user_context.get('phone', 'unknown')}
            - Status: {user_context.get('status', 'active')}
            """
            messages.append({"role": "system", "content": context_msg})
            
            # Add conversation history (last 5 messages for context)
            if conversation_history:
                for msg in conversation_history[-5:]:
                    messages.append(msg)
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Call OpenAI API
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            
            # Extract response
            ai_message = response.choices[0].message.content
            
            # Parse intent from message
            intent_analysis = await AIService._analyze_intent(message, ai_message)
            
            return {
                "intent": intent_analysis["intent"],
                "entities": intent_analysis["entities"],
                "response": ai_message,
                "confidence": intent_analysis["confidence"],
                "requires_confirmation": intent_analysis["requires_confirmation"],
                "next_action": intent_analysis["next_action"]
            }
            
        except Exception as e:
            logger.error(f"AI processing error: {str(e)}")
            return {
                "intent": "error",
                "entities": {},
                "response": "Sorry, I'm having trouble understanding. Could you try again? 🤔",
                "confidence": 0.0,
                "requires_confirmation": False,
                "next_action": None
            }
    
    @staticmethod
    async def _analyze_intent(user_message: str, ai_response: str) -> Dict:
        """
        Analyze user intent from message content.
        """
        input_text = user_message.lower()
        
        # Airtime purchase intent
        if any(word in input_text for word in ["airtime", "recharge", "topup", "top up"]):
            amount = AIService._extract_amount(input_text)
            phone = AIService._extract_phone(input_text)
            network = AIService._extract_network(input_text)
            
            return {
                "intent": "buy_airtime",
                "entities": {
                    "amount": amount,
                    "phone": phone,
                    "network": network
                },
                "confidence": 0.9,
                "requires_confirmation": True,
                "next_action": "confirm_airtime_purchase"
            }
        
        # Data purchase intent
        elif any(word in input_text for word in ["data", "bundle", "gigs", "gb", "mb"]):
            return {
                "intent": "buy_data",
                "entities": {
                    "amount": AIService._extract_amount(input_text),
                    "phone": AIService._extract_phone(input_text),
                    "network": AIService._extract_network(input_text)
                },
                "confidence": 0.9,
                "requires_confirmation": True,
                "next_action": "confirm_data_purchase"
            }
        
        # Electricity purchase intent
        elif any(word in input_text for word in ["electricity", "power", "prepaid", "token", "eskom"]):
            return {
                "intent": "buy_electricity",
                "entities": {
                    "amount": AIService._extract_amount(input_text),
                    "meter_number": AIService._extract_meter_number(input_text)
                },
                "confidence": 0.9,
                "requires_confirmation": True,
                "next_action": "confirm_electricity_purchase"
            }
        
        # Balance check
        elif any(word in input_text for word in ["balance", "wallet", "money", "how much"]):
            return {
                "intent": "check_balance",
                "entities": {},
                "confidence": 0.95,
                "requires_confirmation": False,
                "next_action": None
            }
        
        # Transaction history
        elif any(word in input_text for word in ["history", "transactions", "statement", "purchases"]):
            return {
                "intent": "transaction_history",
                "entities": {},
                "confidence": 0.9,
                "requires_confirmation": False,
                "next_action": None
            }
        
        # Help / Menu
        elif any(word in input_text for word in ["help", "menu", "what can", "how do", "how to"]):
            return {
                "intent": "help",
                "entities": {},
                "confidence": 0.95,
                "requires_confirmation": False,
                "next_action": None
            }
        
        # Greeting
        elif any(word in input_text for word in ["hi", "hello", "hey", "start", "menu"]):
            return {
                "intent": "greeting",
                "entities": {},
                "confidence": 0.95,
                "requires_confirmation": False,
                "next_action": None
            }
        
        # Default to conversation
        return {
            "intent": "conversation",
            "entities": {},
            "confidence": 0.7,
            "requires_confirmation": False,
            "next_action": None
        }
    
    @staticmethod
    def _extract_amount(text: str) -> Optional[float]:
        """Extract monetary amount from text."""
        # Match patterns like: R50, R 50, 50, 50.00
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
    
    @staticmethod
    def _extract_phone(text: str) -> Optional[str]:
        """Extract South African phone number from text."""
        # Patterns: 0821234567, 082 123 4567, +27821234567
        patterns = [
            r'(\+27\d{9})',  # +27821234567
            r'(0\d{9})',  # 0821234567
            r'(0\d{2}\s*\d{3}\s*\d{4})'  # 082 123 4567
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group(1).replace(' ', '')
                return phone
        return None
    
    @staticmethod
    def _extract_network(text: str) -> Optional[str]:
        """Extract mobile network from text."""
        text_lower = text.lower()
        
        if 'mtn' in text_lower:
            return 'MTN'
        elif 'vodacom' in text_lower or 'vodac' in text_lower:
            return 'Vodacom'
        elif 'cell c' in text_lower or 'cellc' in text_lower:
            return 'Cell C'
        elif 'telkom' in text_lower:
            return 'Telkom'
        
        # Try to detect from phone number prefix
        phone = AIService._extract_phone(text)
        if phone:
            if phone.startswith('083') or phone.startswith('084'):
                return 'MTN'
            elif phone.startswith('082') or phone.startswith('072'):
                return 'Vodacom'
            elif phone.startswith('084'):
                return 'Cell C'
            elif phone.startswith('081'):
                return 'Telkom'
        
        return None
    
    @staticmethod
    def _extract_meter_number(text: str) -> Optional[str]:
        """Extract electricity meter number from text."""
        # Meter numbers are typically 11 digits
        pattern = r'\b(\d{11})\b'
        match = re.search(pattern, text)
        if match:
            return match.group(1)
        return None
    
    @staticmethod
    async def process_voice_note(audio_file_path: str) -> Optional[str]:
        """
        Convert voice note to text using OpenAI Whisper.
        
        Args:
            audio_file_path: Path to the audio file (.ogg, .mp3, .wav, .m4a)
        
        Returns:
            Transcribed text or None if failed
        """
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            logger.info(f"Transcribing voice note: {audio_file_path}")
            
            # Open audio file and transcribe
            with open(audio_file_path, "rb") as audio_file:
                transcript = await client.audio.transcriptions.create(
                    model="whisper-1",  # OpenAI's Whisper model
                    file=audio_file,
                    language="en"  # Can also auto-detect
                )
            
            transcribed_text = transcript.text
            logger.info(f"Voice note transcribed successfully: {transcribed_text[:100]}...")
            
            return transcribed_text
            
        except Exception as e:
            logger.error(f"Voice transcription error: {str(e)}")
            return None
    
    @staticmethod
    async def extract_text_from_image(image_path: str) -> Optional[Dict]:
        """
        Extract text from image using GPT-4 Vision (OCR).
        Useful for reading account numbers, meter numbers, etc.
        
        Args:
            image_path: Path to the image file
        
        Returns:
            Dict with extracted information or None if failed
        """
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            logger.info(f"Processing image: {image_path}")
            
            # Read image and encode to base64
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Determine image type
            image_ext = Path(image_path).suffix.lower()
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.webp': 'image/webp',
                '.gif': 'image/gif'
            }
            mime_type = mime_types.get(image_ext, 'image/jpeg')
            
            # Call GPT-4 Vision API
            response = await client.chat.completions.create(
                model="gpt-4o",  # GPT-4 with vision
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """You are analyzing an image to extract utility payment information for a South African user.

CRITICAL: Respond with ONLY a valid JSON object. No explanation, no markdown, no code blocks, just pure JSON.

Extract these fields if visible:
{
    "type": "phone_number" or "meter_number" or "account_number" or "utility_bill" or "unknown",
    "phone_number": "0821234567" (if phone number visible),
    "meter_number": "12345678901" (if electricity meter visible - usually 11 digits),
    "account_number": "any account number visible",
    "provider": "Eskom" or "City Power" or "MTN" or "Vodacom" or "Telkom" or "Cell C" or "Unknown",
    "amount": "R100" (if amount visible on bill),
    "confidence": 0.85 (0.0 to 1.0, how confident you are),
    "description": "brief description of what you see"
}

Examples of correct responses:
{"type": "phone_number", "phone_number": "0821234567", "provider": "MTN", "confidence": 0.95, "description": "MTN phone number on screen"}
{"type": "meter_number", "meter_number": "12345678901", "provider": "Eskom", "confidence": 0.90, "description": "Eskom prepaid meter"}
{"type": "utility_bill", "account_number": "ACC123456", "provider": "City Power", "amount": "R250.50", "confidence": 0.85, "description": "City Power electricity bill"}
{"type": "unknown", "confidence": 0.3, "description": "blurry image, cannot identify numbers"}

IMPORTANT: Return ONLY the JSON object, nothing else. No markdown, no explanations."""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            
            extracted_text = response.choices[0].message.content
            logger.info(f"Image processed successfully: {extracted_text[:100]}...")
            
            # Try to parse as JSON, otherwise return as text
            try:
                import json
                extracted_data = json.loads(extracted_text)
                return {
                    "success": True,
                    "data": extracted_data,
                    "raw_text": extracted_text
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "data": {},
                    "raw_text": extracted_text
                }
            
        except Exception as e:
            logger.error(f"Image processing error: {str(e)}")
            return {
                "success": False,
                "data": {},
                "raw_text": str(e)
            }


# Singleton instance
ai_service = AIService()