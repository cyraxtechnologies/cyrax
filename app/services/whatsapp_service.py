"""
WhatsApp Service
Handles all WhatsApp Business API interactions
"""
import httpx
import logging
from typing import Dict, Optional, List
import aiofiles
import os
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    WhatsApp Business API client for Cyrax.
    """
    
    def __init__(self):
        self.api_url = settings.WHATSAPP_API_URL
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    async def send_text_message(
        self, 
        to_phone: str, 
        message: str,
        preview_url: bool = False
    ) -> Dict:
        """Send a text message to a WhatsApp user."""
        try:
            clean_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_phone,
                "type": "text",
                "text": {
                    "preview_url": preview_url,
                    "body": message
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Message sent to {clean_phone}: {result.get('messages', [{}])[0].get('id')}")
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"WhatsApp API error: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            raise
    
    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en",
        components: Optional[List[Dict]] = None
    ) -> Dict:
        """Send a pre-approved template message."""
        try:
            clean_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            payload = {
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {
                        "code": language_code
                    }
                }
            }
            
            if components:
                payload["template"]["components"] = components
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            logger.error(f"Failed to send template: {str(e)}")
            raise
    
    async def send_interactive_message(
        self,
        to_phone: str,
        header_text: str,
        body_text: str,
        footer_text: str,
        buttons: List[Dict]
    ) -> Dict:
        """Send message with interactive buttons."""
        try:
            clean_phone = to_phone.replace("+", "").replace(" ", "").replace("-", "")
            
            formatted_buttons = [
                {
                    "type": "reply",
                    "reply": {
                        "id": btn["id"],
                        "title": btn["title"][:20]
                    }
                }
                for btn in buttons[:3]
            ]
            
            payload = {
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "header": {
                        "type": "text",
                        "text": header_text[:60]
                    },
                    "body": {
                        "text": body_text[:1024]
                    },
                    "footer": {
                        "text": footer_text[:60]
                    },
                    "action": {
                        "buttons": formatted_buttons
                    }
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            logger.error(f"Failed to send interactive message: {str(e)}")
            raise
    
    async def download_media(self, media_id: str, save_dir: str = "media") -> str:
        """Download media file from WhatsApp."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/{media_id}",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                media_data = response.json()
                
                media_url = media_data.get("url")
                mime_type = media_data.get("mime_type", "")
                
                download_response = await client.get(
                    media_url,
                    headers=self.headers,
                    timeout=60.0
                )
                download_response.raise_for_status()
                
                os.makedirs(save_dir, exist_ok=True)
                
                extension = mime_type.split("/")[-1] if "/" in mime_type else "bin"
                filename = f"{media_id}_{datetime.now().timestamp()}.{extension}"
                filepath = os.path.join(save_dir, filename)
                
                async with aiofiles.open(filepath, "wb") as f:
                    await f.write(download_response.content)
                
                logger.info(f"Media downloaded: {filepath}")
                return filepath
                
        except Exception as e:
            logger.error(f"Failed to download media: {str(e)}")
            raise
    
    async def mark_message_read(self, message_id: str) -> Dict:
        """Mark a message as read."""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/{self.phone_number_id}/messages",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            logger.error(f"Failed to mark message read: {str(e)}")
            return {}
    
    @staticmethod
    def parse_webhook_message(webhook_data: Dict) -> Optional[Dict]:
        """Parse incoming webhook data from WhatsApp."""
        try:
            entry = webhook_data.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            
            if "messages" not in value:
                return None
            
            message = value["messages"][0]
            contact = value["contacts"][0]
            
            parsed = {
                "message_id": message.get("id"),
                "from_phone": message.get("from"),
                "from_name": contact.get("profile", {}).get("name", ""),
                "timestamp": message.get("timestamp"),
                "type": message.get("type"),
            }
            
            if parsed["type"] == "text":
                parsed["text"] = message.get("text", {}).get("body", "")
            
            elif parsed["type"] == "image":
                parsed["media_id"] = message.get("image", {}).get("id")
                parsed["mime_type"] = message.get("image", {}).get("mime_type")
                parsed["caption"] = message.get("image", {}).get("caption", "")
            
            elif parsed["type"] == "audio":
                parsed["media_id"] = message.get("audio", {}).get("id")
                parsed["mime_type"] = message.get("audio", {}).get("mime_type")
            
            elif parsed["type"] == "video":
                parsed["media_id"] = message.get("video", {}).get("id")
                parsed["mime_type"] = message.get("video", {}).get("mime_type")
                parsed["caption"] = message.get("video", {}).get("caption", "")
            
            elif parsed["type"] == "document":
                parsed["media_id"] = message.get("document", {}).get("id")
                parsed["mime_type"] = message.get("document", {}).get("mime_type")
                parsed["filename"] = message.get("document", {}).get("filename", "")
            
            elif parsed["type"] == "button":
                parsed["button_payload"] = message.get("button", {}).get("payload")
                parsed["button_text"] = message.get("button", {}).get("text")
            
            elif parsed["type"] == "interactive":
                interactive = message.get("interactive", {})
                parsed["interactive_type"] = interactive.get("type")
                
                if parsed["interactive_type"] == "button_reply":
                    parsed["button_id"] = interactive.get("button_reply", {}).get("id")
                    parsed["button_title"] = interactive.get("button_reply", {}).get("title")
            
            return parsed
            
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse webhook: {str(e)}")
            return None
    
    @staticmethod
    def verify_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
        """Verify webhook during setup."""
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("Webhook verified successfully")
            return challenge
        
        logger.warning(f"Webhook verification failed: mode={mode}, token_match={token == settings.WHATSAPP_VERIFY_TOKEN}")
        return None


# Singleton instance
whatsapp_service = WhatsAppService()
