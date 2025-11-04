"""
Twilio WhatsApp Service
Handles WhatsApp messaging via Twilio
"""
import httpx
import logging
from typing import Dict, Optional
from base64 import b64encode

from app.config import settings

logger = logging.getLogger(__name__)


class TwilioWhatsAppService:
    """
    Twilio WhatsApp client for sending/receiving messages.
    """
    
    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.from_number = settings.TWILIO_WHATSAPP_NUMBER
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}"
        
        # Create basic auth header
        credentials = b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    
    async def send_message(self, to_phone: str, message: str) -> Dict:
        """
        Send a WhatsApp message via Twilio.
        
        Args:
            to_phone: Recipient phone (format: +27821234567)
            message: Message text
            
        Returns:
            Response from Twilio
        """
        try:
            # Clean phone number
            if not to_phone.startswith("+"):
                to_phone = f"+{to_phone}"
            
            # Add whatsapp: prefix
            to_whatsapp = f"whatsapp:{to_phone}"
            
            # Prepare data
            data = {
                "From": self.from_number,
                "To": to_whatsapp,
                "Body": message
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/Messages.json",
                    headers=self.headers,
                    data=data,
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Message sent to {to_phone}: {result.get('sid')}")
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Twilio API error: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            raise
    
    @staticmethod
    def parse_webhook(form_data: Dict) -> Optional[Dict]:
        """
        Parse incoming webhook from Twilio.
        
        Args:
            form_data: Form data from Twilio webhook
            
        Returns:
            Parsed message data
        """
        try:
            # Twilio sends form data, not JSON
            from_number = form_data.get("From", "").replace("whatsapp:", "")
            body = form_data.get("Body", "")
            message_sid = form_data.get("MessageSid", "")
            profile_name = form_data.get("ProfileName", "")
            
            return {
                "message_id": message_sid,
                "from_phone": from_number,
                "from_name": profile_name,
                "text": body,
                "type": "text",
                "timestamp": None
            }
            
        except Exception as e:
            logger.error(f"Failed to parse webhook: {str(e)}")
            return None


# Singleton instance
twilio_whatsapp = TwilioWhatsAppService()