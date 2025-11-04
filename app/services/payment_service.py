"""
Payment Service
Handles all payment processing via PayStack
"""
import httpx
import logging
import hashlib
import hmac
from typing import Dict, Optional
from decimal import Decimal

from app.config import settings

logger = logging.getLogger(__name__)


class PayStackService:
    """
    PayStack API client for processing payments in South Africa.
    """
    
    def __init__(self):
        self.base_url = settings.PAYSTACK_BASE_URL
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
    
    async def initialize_payment(
        self,
        email: str,
        amount: float,
        reference: str,
        callback_url: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Initialize a payment transaction."""
        try:
            amount_kobo = int(Decimal(str(amount)) * 100)
            
            payload = {
                "email": email,
                "amount": amount_kobo,
                "reference": reference,
                "currency": "ZAR"
            }
            
            if callback_url:
                payload["callback_url"] = callback_url
            
            if metadata:
                payload["metadata"] = metadata
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/transaction/initialize",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("status"):
                    logger.info(f"Payment initialized: {reference}")
                    return result.get("data", {})
                else:
                    raise Exception(result.get("message", "Payment initialization failed"))
                    
        except httpx.HTTPStatusError as e:
            logger.error(f"PayStack API error: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize payment: {str(e)}")
            raise
    
    async def verify_payment(self, reference: str) -> Dict:
        """Verify a payment transaction."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/transaction/verify/{reference}",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("status"):
                    data = result.get("data", {})
                    logger.info(f"Payment verified: {reference} - {data.get('status')}")
                    return data
                else:
                    raise Exception(result.get("message", "Payment verification failed"))
                    
        except Exception as e:
            logger.error(f"Failed to verify payment: {str(e)}")
            raise
    
    async def buy_airtime(
        self,
        phone_number: str,
        amount: float,
        provider: str
    ) -> Dict:
        """Purchase airtime using PayStack's Bills Payment API."""
        try:
            provider_map = {
                "mtn": "mtn",
                "vodacom": "vodacom",
                "cellc": "cellc",
                "telkom": "telkom"
            }
            
            bill_code = provider_map.get(provider.lower())
            if not bill_code:
                raise ValueError(f"Unsupported provider: {provider}")
            
            amount_kobo = int(Decimal(str(amount)) * 100)
            
            payload = {
                "type": "airtime",
                "amount": amount_kobo,
                "phone": phone_number,
                "service_type": bill_code
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/bill/pay",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("status"):
                    logger.info(f"Airtime purchased: {phone_number} - R{amount}")
                    return result.get("data", {})
                else:
                    raise Exception(result.get("message", "Airtime purchase failed"))
                    
        except Exception as e:
            logger.error(f"Failed to buy airtime: {str(e)}")
            raise
    
    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        """Verify webhook signature from PayStack."""
        try:
            expected_signature = hmac.new(
                settings.PAYSTACK_WEBHOOK_SECRET.encode(),
                payload,
                hashlib.sha512
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            logger.error(f"Webhook signature verification failed: {str(e)}")
            return False


# Singleton instance
paystack_service = PayStackService()