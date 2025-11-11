"""
Enhanced WhatsApp Router with Voice & Image Support
Handles text, voice notes, and images via Twilio WhatsApp
"""
from fastapi import APIRouter, Request, Depends, BackgroundTasks
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict
import logging
from datetime import datetime
import aiofiles
import os
from pathlib import Path
import httpx

from app.database import get_db
from app.models.user import User, UserStatus
from app.models.conversation import Conversation
from app.services.twilio_service import twilio_whatsapp
from app.services.transaction_service import transaction_service
from app.services.security_service import security_service

# Import the AI service (now enhanced with voice & image)
from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Media storage directory
MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)


@router.post("/")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Main webhook endpoint for receiving WhatsApp messages from Twilio."""
    try:
        form_data = await request.form()
        logger.info(f"Webhook received: {dict(form_data)}")
        
        message = twilio_whatsapp.parse_webhook(dict(form_data))
        
        if not message:
            return PlainTextResponse("OK")
        
        background_tasks.add_task(
            process_message,
            message,
            db
        )
        
        return PlainTextResponse("OK")
        
    except Exception as e:
        logger.error(f"Webhook processing error: {str(e)}")
        return PlainTextResponse("ERROR")


async def process_message(message: dict, db: Session):
    """
    Process incoming WhatsApp message with support for:
    - Text messages
    - Voice notes (transcribed with Whisper)
    - Images (OCR with GPT-4 Vision)
    """
    try:
        phone_number = message.get("from_phone")
        message_id = message.get("message_id")
        message_type = message.get("type")
        
        logger.info(f"Processing {message_type} message from {phone_number}")
        
        # Get or create user
        user = db.query(User).filter(User.phone_number == phone_number).first()
        if not user:
            user = User(
                phone_number=phone_number,
                whatsapp_name=message.get("from_name"),
                status=UserStatus.ACTIVE  # Auto-activate for utility bill service
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            await send_welcome_message(phone_number, message.get("from_name"))
            return
        
        user.last_active_at = datetime.utcnow()
        db.commit()
        
        # Extract message text based on type
        message_text = ""
        
        if message_type == "text":
            message_text = message.get("text", "")
            
        elif message_type == "audio":
            # Download and transcribe voice note
            message_text = await handle_voice_note(message)
            if not message_text:
                await twilio_whatsapp.send_message(
                    phone_number,
                    "Sorry, I couldn't understand your voice note. Please try again or send a text message. 🎤"
                )
                return
            
            # Send confirmation that we understood
            await twilio_whatsapp.send_message(
                phone_number,
                f"🎤 I heard: \"{message_text}\"\n\nLet me help you with that..."
            )
            
        elif message_type == "image":
            # Download and process image with OCR
            image_result = await handle_image(message)
            
            if image_result and image_result.get("success"):
                extracted_data = image_result.get("data", {})
                confidence = extracted_data.get("confidence", 0)
                
                # Check if extraction was successful
                if confidence < 0.5:
                    await twilio_whatsapp.send_message(
                        phone_number,
                        "📸 I can see your image, but it's not clear enough. Please try:\n• Better lighting\n• Closer shot\n• Focus on the numbers"
                    )
                    return
                
                image_type = extracted_data.get("type", "unknown")
                
                # PHONE NUMBER DETECTED - Airtime Intent
                if image_type == "phone_number" or "phone_number" in extracted_data:
                    phone = extracted_data.get("phone_number", "")
                    provider = extracted_data.get("provider", "Unknown")
                    
                    if phone:
                        await twilio_whatsapp.send_message(
                            phone_number,
                            f"📱 I found:\n• Phone: {phone}\n• Network: {provider}\n\nHow much airtime would you like to buy?"
                        )
                        # Set intent for airtime purchase
                        message_text = f"buy airtime for {phone}"
                    else:
                        await twilio_whatsapp.send_message(
                            phone_number,
                            "📱 I see a phone number but couldn't read it clearly. Please type it or send a clearer photo."
                        )
                        return
                
                # METER NUMBER DETECTED - Electricity Intent
                elif image_type == "meter_number" or "meter_number" in extracted_data:
                    meter = extracted_data.get("meter_number", "")
                    provider = extracted_data.get("provider", "Eskom")
                    
                    if meter:
                        await twilio_whatsapp.send_message(
                            phone_number,
                            f"⚡ I found:\n• Meter: {meter}\n• Provider: {provider}\n\nHow much electricity would you like to buy? (e.g., R50, R100)"
                        )
                        # Set intent for electricity purchase
                        message_text = f"buy electricity for meter {meter}"
                    else:
                        await twilio_whatsapp.send_message(
                            phone_number,
                            "⚡ I see an electricity meter but couldn't read the number. Please type it or send a clearer photo."
                        )
                        return
                
                # UTILITY BILL DETECTED - Bill Payment Intent
                elif image_type == "utility_bill" or "account_number" in extracted_data:
                    account = extracted_data.get("account_number", "")
                    provider = extracted_data.get("provider", "Unknown")
                    amount = extracted_data.get("amount", "")
                    
                    bill_msg = f"📄 I found a {provider} bill:\n"
                    if account:
                        bill_msg += f"• Account: {account}\n"
                    if amount:
                        bill_msg += f"• Amount Due: {amount}\n"
                    bill_msg += "\nWould you like to pay this bill? Reply YES to confirm."
                    
                    await twilio_whatsapp.send_message(phone_number, bill_msg)
                    # Set intent for bill payment
                    message_text = f"pay {provider} bill for account {account} amount {amount}"
                
                # UNKNOWN/UNCLEAR IMAGE
                else:
                    description = extracted_data.get("description", "an image")
                    await twilio_whatsapp.send_message(
                        phone_number,
                        f"📸 I see {description}, but I couldn't identify:\n• Phone number (for airtime)\n• Meter number (for electricity)\n• Utility bill (for payment)\n\nPlease try:\n✓ Close-up of the number\n✓ Good lighting\n✓ Clear focus"
                    )
                    # Still pass to AI for general processing
                    message_text = "help"
            
            else:
                await twilio_whatsapp.send_message(
                    phone_number,
                    "Sorry, I couldn't process your image. Please try again with a clearer photo! 📸"
                )
                return
        
        else:
            await twilio_whatsapp.send_message(
                phone_number,
                f"I support text messages, voice notes, and images. Please send one of these! 💬🎤📸"
            )
            return
        
        # Save conversation
        conversation = Conversation(
            user_id=user.id,
            phone_number=phone_number,
            message_id=message_id,
            message_type=message_type,
            direction="inbound",
            message_text=message_text
        )
        db.add(conversation)
        db.commit()
        
        # Get user context
        user_context = {
            "name": user.full_name,
            "phone": user.phone_number,
            "balance": user.balance,
            "status": user.status.value
        }
        
        # Get conversation history
        history = db.query(Conversation).filter(
            Conversation.user_id == user.id,
            Conversation.is_processed == True
        ).order_by(Conversation.created_at.desc()).limit(5).all()
        
        conversation_history = []
        for conv in reversed(history):
            if conv.message_text:
                conversation_history.append({"role": "user", "content": conv.message_text})
            if conv.ai_response:
                conversation_history.append({"role": "assistant", "content": conv.ai_response})
        
        # Process with AI
        ai_result = await ai_service.process_message(
            message_text,
            user_context,
            conversation_history
        )
        
        # Update conversation with AI response
        conversation.ai_response = ai_result["response"]
        conversation.intent_detected = ai_result["intent"]
        conversation.entities_extracted = ai_result["entities"]
        conversation.confidence_score = ai_result["confidence"]
        conversation.is_processed = True
        conversation.processed_at = datetime.utcnow()
        db.commit()
        
        # Send AI response
        await twilio_whatsapp.send_message(phone_number, ai_result["response"])
        
        # Handle specific intents
        if ai_result["intent"] == "help" or ai_result["intent"] == "greeting":
            await send_menu(phone_number)
        
    except Exception as e:
        logger.error(f"Message processing error: {str(e)}", exc_info=True)
        await twilio_whatsapp.send_message(
            phone_number,
            "Sorry, something went wrong. Please try again later. 😅"
        )


async def handle_voice_note(message: dict) -> Optional[str]:
    """
    Download and transcribe voice note using Whisper.
    """
    try:
        media_url = message.get("media_url")
        if not media_url:
            return None
        
        # Download audio file
        audio_path = await download_media(
            media_url,
            message.get("message_id"),
            "ogg"  # Twilio sends .ogg format
        )
        
        if not audio_path:
            return None
        
        # Transcribe with Whisper
        transcribed_text = await ai_service.process_voice_note(str(audio_path))
        
        # Clean up file
        try:
            os.remove(audio_path)
        except:
            pass
        
        return transcribed_text
        
    except Exception as e:
        logger.error(f"Voice note handling error: {str(e)}")
        return None


async def handle_image(message: dict) -> Optional[Dict]:
    """
    Download and process image with GPT-4 Vision (OCR).
    """
    try:
        media_url = message.get("media_url")
        if not media_url:
            return None
        
        # Download image
        image_path = await download_media(
            media_url,
            message.get("message_id"),
            "jpg"  # Default to jpg
        )
        
        if not image_path:
            return None
        
        # Process with GPT-4 Vision
        result = await ai_service.extract_text_from_image(str(image_path))
        
        # Clean up file
        try:
            os.remove(image_path)
        except:
            pass
        
        return result
        
    except Exception as e:
        logger.error(f"Image handling error: {str(e)}")
        return None


async def download_media(media_url: str, message_id: str, extension: str) -> Optional[Path]:
    """
    Download media file from Twilio.
    Twilio returns 307 redirects to their CDN, so we must follow them.
    """
    try:
        # Twilio media URLs require authentication
        from app.config import settings
        
        # CRITICAL: follow_redirects=True to handle Twilio's 307 redirects
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                media_url,
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                timeout=30.0
            )
            response.raise_for_status()
            
            # Save to file
            filename = f"{message_id}.{extension}"
            filepath = MEDIA_DIR / filename
            
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(response.content)
            
            logger.info(f"Media downloaded: {filepath}")
            return filepath
            
    except Exception as e:
        logger.error(f"Media download error: {str(e)}")
        return None


async def send_welcome_message(phone_number: str, name: str):
    """Send welcome message to new users."""
    welcome = f"""👋 Hi {name}! Welcome to Cyrax!

I'm your AI utility bill assistant. I can help you:

💳 Buy Airtime (MTN, Vodacom, Cell C, Telkom)
📱 Buy Data Bundles
⚡ Pay Electricity (prepaid tokens)
💰 Check Your Balance
📊 View Transaction History

Just tell me what you need in plain language - I understand English, voice notes, and even photos! 🎤📸

Try: "Buy R50 airtime" or "Check balance"

🔜 Money transfers coming soon once we get our banking license!"""
    
    await twilio_whatsapp.send_message(phone_number, welcome)


async def send_menu(phone_number: str):
    """Send menu options."""
    menu = """📋 *What I Can Do:*

1️⃣ *Buy Airtime*
   "Buy R50 MTN airtime for 0821234567"

2️⃣ *Buy Data*
   "Buy 1GB Vodacom data"

3️⃣ *Pay Electricity*
   "Pay R100 electricity for meter 12345678901"

4️⃣ *Check Balance*
   "What's my balance?"

5️⃣ *Transaction History*
   "Show my transactions"

💡 Tip: You can also send voice notes or photos of meter numbers!"""
    
    await twilio_whatsapp.send_message(phone_number, menu)