"""
WhatsApp API Service
Third-party WhatsApp integration via CRM
"""
import httpx
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class WhatsAppAPIService:
    """
    WhatsApp API client using third-party CRM.
    """
    
    def __init__(self):
        from app.config import settings
        self.base_url = settings.WHATSAPP_API_URL
        self.api_key = settings.WHATSAPP_API_KEY
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.version = "v19.0"
    
    async def send_typing_indicator(self, to_phone: str, duration: int = 2) -> None:
        """
        Show typing indicator (...) to user.
        
        Args:
            to_phone: Recipient phone
            duration: How long to show typing (seconds)
        """
        try:
            import asyncio
            
            phone = to_phone.replace("+", "").replace(" ", "")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Send typing indicator
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "typing"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{self.base_url}/{self.version}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=headers
                )
            
            # Wait for specified duration
            await asyncio.sleep(duration)
            
            logger.info(f"Typing indicator shown to {phone}")
            
        except Exception as e:
            logger.error(f"Failed to send typing indicator: {str(e)}")
            # Don't raise - typing is optional


    async def send_message(self, to_phone: str, message: str) -> Dict:
        """
        Send WhatsApp message via Cloud API.
        
        Args:
            to_phone: Recipient phone (format: 27821234567 - no +)
            message: Message text
            
        Returns:
            Response from API
        """
        try:
            # Clean phone number - remove + if present
            phone = to_phone.replace("+", "").replace(" ", "")
            
            # WhatsApp Cloud API format
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Payload per WhatsApp Cloud API docs
            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "text",
                "text": {
                    "body": message
                }
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/{self.version}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Message sent to {phone}: Success")
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp API error: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            raise
    
    async def send_delay(self, duration: float = 1.5) -> None:
        """
        Add natural delay before sending message (simulates typing).
        No visible indicator, just pause.
        
        Args:
            duration: Seconds to wait
        """
        import asyncio
        await asyncio.sleep(duration)
    
    async def send_buttons(self, to_phone: str, body_text: str, buttons: List[Dict]) -> Dict:
        """
        Send interactive button message.
        
        Args:
            to_phone: Recipient phone
            body_text: Main message text
            buttons: List of buttons [{"id": "yes", "title": "Yes"}, ...]
            
        Returns:
            Response from API
        """
        try:
            phone = to_phone.replace("+", "").replace(" ", "")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Interactive buttons payload
            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": body_text
                    },
                    "action": {
                        "buttons": buttons[:3]  # Max 3 buttons
                    }
                }
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/{self.version}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Buttons sent to {phone}: Success")
                return result
                
        except Exception as e:
            logger.error(f"Failed to send buttons: {str(e)}")
            # Fallback to text if buttons fail
            return await self.send_message(to_phone, body_text)
    
    @staticmethod
    def parse_webhook(data: Dict) -> Optional[Dict]:
        """
        Parse incoming webhook from WhatsApp API.
        
        Returns:
            {
                "from_phone": "+27...",
                "from_name": "User Name",
                "message_id": "msg_123",
                "type": "text|audio|image",
                "text": "message content",
                "media_url": "https://...",
                "media_id": "media_123",
                "timestamp": "2025-11-11T..."
            }
        """
        try:
            # WhatsApp Cloud API format
            if "entry" in data:
                entry = data.get("entry", [{}])[0]
                changes = entry.get("changes", [{}])[0]
                value = changes.get("value", {})
                
                messages = value.get("messages", [])
                if not messages:
                    return None
                
                message = messages[0]
                contacts = value.get("contacts", [{}])[0]
                
                # Extract phone number (add country code if not present)
                from_phone = message.get("from", "")
                if from_phone and not from_phone.startswith("+"):
                    from_phone = f"+{from_phone}"
                
                message_type = message.get("type", "text")
                
                result = {
                    "from_phone": from_phone,
                    "from_name": contacts.get("profile", {}).get("name", ""),
                    "message_id": message.get("id", ""),
                    "type": message_type,
                    "text": message.get("text", {}).get("body", "") if message_type == "text" else "",
                    "caption": message.get(message_type, {}).get("caption", "") if message_type in ["image", "video", "document"] else "",
                    "timestamp": message.get("timestamp", "")
                }
                
                # Handle button clicks (interactive type)
                if message_type == "interactive":
                    interactive = message.get("interactive", {})
                    
                    # Check if it's a Flow response
                    if interactive.get("type") == "nfm_reply":
                        nfm_reply = interactive.get("nfm_reply", {})
                        response_json = nfm_reply.get("response_json", "{}")
                        result["text"] = "FLOW_RESPONSE"
                        result["flow_data"] = response_json  # Store Flow data
                        result["type"] = "text"
                        logger.info(f"Flow response received: {response_json[:100]}")
                    else:
                        # Regular button click
                        button_reply = interactive.get("button_reply", {})
                        result["text"] = button_reply.get("id", "")
                        result["type"] = "text"
                        logger.info(f"Button clicked: {result['text']}")
                
                # Handle media - get media_id to fetch URL later
                if message_type in ["image", "audio", "video", "document"]:
                    media = message.get(message_type, {})
                    result["media_id"] = media.get("id", "")
                    result["mime_type"] = media.get("mime_type", "")
                    # Note: media_url will be fetched using media_id in download_media function
                
                logger.info(f"Parsed webhook: type={message_type}, media_id={result.get('media_id', 'none')}")
                return result
            
            # Fallback for other formats
            return None
            
        except Exception as e:
            logger.error(f"Webhook parsing error: {str(e)}")
            return None
    async def send_quick_replies(self, to_phone: str, body_text: str, buttons: List[Dict]) -> Dict:
        """
        Send message with quick reply buttons (up to 3).
        Same as send_buttons but with better name.
        
        Args:
            to_phone: Recipient phone
            body_text: Main message text
            buttons: [{"id": "airtime", "title": "Buy Airtime"}, ...]
            
        Returns:
            Response from API
        """
        try:
            phone = to_phone.replace("+", "").replace(" ", "")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Format buttons for WhatsApp API
            formatted_buttons = []
            for btn in buttons[:3]:  # Max 3
                formatted_buttons.append({
                    "type": "reply",
                    "reply": {
                        "id": btn.get("id", "btn"),
                        "title": btn.get("title", "Button")[:20]  # Max 20 chars
                    }
                })
            
            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {
                        "text": body_text
                    },
                    "action": {
                        "buttons": formatted_buttons
                    }
                }
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/{self.version}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Quick replies sent to {phone}")
                return result
                
        except Exception as e:
            logger.error(f"Failed to send quick replies: {str(e)}")
            # Fallback to text
            return await self.send_message(to_phone, body_text)


    async def get_media_url(self, media_id: str) -> Optional[str]:
        """
        Get media URL from media_id.
        Note: This CRM returns the media file directly, not a JSON with URL.
        We'll save it and return a local file path instead.
        
        Args:
            media_id: Media ID from webhook
            
        Returns:
            The URL to fetch media (same as input since CRM returns file directly)
        """
        try:
            # For this CRM, the media endpoint returns the file directly
            # So we construct the URL and return it for download_media to use
            media_url = f"{self.base_url}/{self.version}/{media_id}"
            logger.info(f"Media URL constructed: {media_url}")
            return media_url
                
        except Exception as e:
            logger.error(f"Failed to construct media URL: {str(e)}")
            return None
    async def send_flow(self, to_phone: str, body_text: str, button_text: str, flow_id: str) -> Dict:
        """
        Send WhatsApp Flow (interactive form).
        
        Args:
            to_phone: Recipient phone
            body_text: Main message text
            button_text: Button text (e.g., "Complete Registration")
            flow_id: Your Flow ID from Meta
            
        Returns:
            Response from API
        """
        try:
            phone = to_phone.replace("+", "").replace(" ", "")
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            # Flow message payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "interactive",
                "interactive": {
                    "type": "flow",
                    "body": {
                        "text": body_text
                    },
                    "action": {
                        "name": "flow",
                        "parameters": {
                            "flow_message_version": "3",
                            "flow_token": f"reg_{phone}",
                            "flow_id": flow_id,
                            "flow_name": "cyrax sign up",
                            "flow_cta": button_text,
                            "flow_action": "navigate",
                            "mode": "draft"  # Allow draft flows for testing
                        }
                    }
                }
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/{self.version}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Flow sent to {phone}: Success")
                return result
                
        except Exception as e:
            logger.error(f"Failed to send flow: {str(e)}")
            # Fallback to buttons if Flow fails
            return await self.send_buttons(
                to_phone,
                body_text,
                [{"type": "reply", "reply": {"id": "register", "title": button_text}}]
            )


# Singleton instance
whatsapp_api = WhatsAppAPIService()