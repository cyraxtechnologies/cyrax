"""
AI Service
Handles all AI interactions using OpenAI GPT-4
"""
from typing import Dict, List, Optional
import re
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class AIService:
    """
    AI service for processing user messages with Cyrax personality.
    """
    
    SYSTEM_PROMPT = """You are Cyrax, a friendly AI financial assistant for South African users on WhatsApp. 

Your role:
- Help users send money, pay bills, buy airtime/data, check balances
- Understand South African slang, accents, and languages (English, Afrikaans, Zulu, Xhosa)
- Be conversational, warm, and helpful
- Ask clarifying questions when needed
- Explain fees and limits clearly

Key capabilities:
1. Send money to phone numbers or account numbers
2. Pay electricity bills (prepaid)
3. Buy airtime and data bundles
4. Check account balance and transaction history
5. Set up recurring payments

Important rules:
- ALWAYS confirm transaction details before processing
- NEVER process a transaction without explicit user confirmation
- Ask for PIN when processing transactions
- Be security-conscious
- Explain any fees upfront

South African context:
- Currency is ZAR (Rand), use R symbol
- Common amounts: R10, R50, R100, R500, R1000
- Mobile providers: MTN, Vodacom, Cell C, Telkom
- Electricity provider: Eskom (and municipalities)

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
            - Balance: R{user_context.get('balance', 0):.2f}
            - Daily Limit Remaining: R{user_context.get('daily_limit_remaining', 0):.2f}
            - Phone: {user_context.get('phone', 'unknown')}
            - FICA Status: {'Verified' if user_context.get('is_fica_compliant') else 'Pending'}
            """
            messages.append({"role": "system", "content": context_msg})
            
            # Add conversation history
            if conversation_history:
                for msg in conversation_history[-5:]:
                    messages.append(msg)
            
            # Add current message
            messages.append({"role": "user", "content": message})
            
            # Call OpenAI with new API
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            
            # Extract response
            ai_message = response.choices[0].message
            
            # Simple intent detection from response
            response_text = ai_message.content.lower()
            input_text = message.lower()
            
            # Detect intent from input and response
            if "send" in input_text and ("money" in input_text or "r" in input_text):
                # Extract amount from input
                amount_match = re.search(r'r?\s*(\d+)', input_text)
                amount = float(amount_match.group(1)) if amount_match else 0
                
                # Extract recipient name
                name_match = re.search(r'to\s+(\w+)', input_text)
                recipient_name = name_match.group(1) if name_match else "recipient"
                
                return {
                    "intent": "send_money",
                    "entities": {
                        "amount": amount,
                        "recipient_name": recipient_name
                    },
                    "response": ai_message.content,
                    "confidence": 0.9,
                    "requires_confirmation": True,
                    "next_action": "confirm_transaction"
                }
            
            elif "airtime" in input_text:
                amount_match = re.search(r'r?\s*(\d+)', input_text)
                amount = float(amount_match.group(1)) if amount_match else 0
                
                return {
                    "intent": "airtime_purchase",
                    "entities": {"amount": amount},
                    "response": ai_message.content,
                    "confidence": 0.85,
                    "requires_confirmation": True,
                    "next_action": "confirm_transaction"
                }
            
            elif "balance" in input_text or "check" in input_text:
                return {
                    "intent": "check_balance",
                    "entities": {},
                    "response": ai_message.content,
                    "confidence": 0.9,
                    "requires_confirmation": False,
                    "next_action": None
                }
            
            elif "history" in input_text or "transactions" in input_text:
                return {
                    "intent": "transaction_history",
                    "entities": {},
                    "response": ai_message.content,
                    "confidence": 0.9,
                    "requires_confirmation": False,
                    "next_action": None
                }
            
            # Default to conversation
            return {
                "intent": "conversation",
                "entities": {},
                "response": ai_message.content,
                "confidence": 0.8,
                "requires_confirmation": False,
                "next_action": None
            }
            
        except Exception as e:
            logger.error(f"AI processing error: {str(e)}")
            return {
                "intent": "error",
                "entities": {},
                "response": "Sorry, I didn't quite understand that. Could you rephrase?",
                "confidence": 0.0,
                "requires_confirmation": False,
                "next_action": None
            }
    
    @staticmethod
    async def process_voice_note(audio_file_path: str) -> str:
        """
        Convert voice note to text using Whisper.
        """
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            with open(audio_file_path, "rb") as audio_file:
                transcript = await client.audio.transcriptions.create(
                    model=settings.OPENAI_WHISPER_MODEL,
                    file=audio_file,
                    language="en"
                )
            return transcript.text
        except Exception as e:
            logger.error(f"Voice transcription error: {str(e)}")
            return ""
    
    @staticmethod
    async def extract_account_from_image(image_path: str) -> Optional[str]:
        """
        Extract account number from screenshot using GPT-4 Vision.
        """
        try:
            from openai import AsyncOpenAI
            import base64
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode()
            
            response = await client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract the account number from this banking screenshot. Return ONLY the account number, nothing else."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=100
            )
            
            account_number = response.choices[0].message.content.strip()
            
            if re.match(r'^\d{8,16}$', account_number):
                return account_number
            
            return None
            
        except Exception as e:
            logger.error(f"Image OCR error: {str(e)}")
            return None
    
    @staticmethod
    def generate_confirmation_message(intent: str, entities: Dict) -> str:
        """Generate a confirmation message for transactions."""
        if intent == "send_money":
            recipient = entities.get('recipient_name') or entities.get('recipient', 'recipient')
            amount = entities.get('amount')
            fee = amount * 0.01
            return f"""Please confirm:

Send R{amount:.2f} to {recipient}
Transaction fee: R{fee:.2f}
Total: R{amount + fee:.2f}

Reply 'YES' to confirm or 'NO' to cancel."""

        elif intent == "airtime_purchase":
            amount = entities.get('amount')
            phone = entities.get('phone_number', 'your number')
            provider = entities.get('provider', '')
            return f"""Please confirm:

Buy R{amount:.2f} {provider} airtime for {phone}
Fee: R1.00
Total: R{amount + 1:.2f}

Reply 'YES' to confirm or 'NO' to cancel."""

        elif intent == "electricity_purchase":
            amount = entities.get('amount')
            meter = entities.get('meter_number', 'your meter')
            return f"""Please confirm:

Buy R{amount:.2f} prepaid electricity
Meter: {meter}
Fee: R2.50
Total: R{amount + 2.50:.2f}

Reply 'YES' to confirm or 'NO' to cancel."""
        
        return "Please confirm this transaction. Reply 'YES' or 'NO'."
