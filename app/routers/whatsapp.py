"""
Enhanced WhatsApp Router with Onboarding, Voice & Image Support
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
from app.services.whatsapp_api_service import whatsapp_api  # ← UPDATED: WhatsApp API
from app.services.transaction_service import transaction_service
from app.services.security_service import security_service
from app.services.onboarding_service import onboarding_service

# Import the AI service (now enhanced with voice & image)
from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Media storage directory
MEDIA_DIR = Path("media")
MEDIA_DIR.mkdir(exist_ok=True)


@router.get("/")
async def verify_webhook(request: Request):
    """
    Meta webhook verification endpoint.
    When you add webhook URL in CRM dashboard, Meta sends GET request with 'challange' parameter.
    Must respond with the same challange value to verify.
    """
    challenge = request.query_params.get("challange")  # Note: their typo in docs
    if challenge:
        logger.info(f"Webhook verification: responding with challenge")
        return PlainTextResponse(challenge)
    return PlainTextResponse("No challenge parameter")


@router.post("/")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Main webhook endpoint for receiving WhatsApp messages."""
    try:
        # Try to parse as JSON first (WhatsApp API format)
        try:
            data = await request.json()
            logger.info(f"Webhook received (JSON): {data}")
            message = whatsapp_api.parse_webhook(data)
        except:
            # Fallback to form data (Twilio format - for backwards compatibility)
            form_data = await request.form()
            logger.info(f"Webhook received (Form): {dict(form_data)}")
            # Convert form to dict for parsing
            message = whatsapp_api.parse_webhook(dict(form_data))
        
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
    - User onboarding (NEW!)
    """
    try:
        phone_number = message.get("from_phone")
        message_id = message.get("message_id")
        message_type = message.get("type")
        from_name = message.get("from_name", "")
        
        logger.info(f"Processing {message_type} message from {phone_number}")
        
        # Get or create user
        user = db.query(User).filter(User.phone_number == phone_number).first()
        
        # NEW: Check if this is a brand new user
        if not user:
            user = User(
                phone_number=phone_number,
                whatsapp_name=from_name,
                status=UserStatus.PENDING_VERIFICATION  # Start as pending
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Send welcome message explaining onboarding
            await send_welcome_message_new_user(phone_number, from_name)
            return
        
        # NEW: Check if user needs to complete onboarding
        if onboarding_service.should_onboard_user(user):
            # Send welcome Flow for new users only
            await send_welcome_message_new_user(phone_number, user.whatsapp_name or "there")
            return
        
        # User is fully onboarded - proceed with normal processing
        user.last_active_at = datetime.utcnow()
        db.commit()
        
        # Extract message text based on type
        message_text = ""
        
        if message_type == "text":
            message_text = message.get("text", "")
            
            # Handle Flow response
            if message_text == "FLOW_RESPONSE":
                flow_data_json = message.get("flow_data", "{}")
                try:
                    import json
                    flow_data = json.loads(flow_data_json)
                    
                    # Process onboarding with Flow data
                    success, msg, updated_user = await onboarding_service.process_flow_response(
                        phone_number,
                        flow_data,
                        db
                    )
                    
                    await whatsapp_api.send_message(phone_number, msg)
                    
                    if success:
                        await send_menu(phone_number)
                    
                    return
                except Exception as e:
                    logger.error(f"Flow processing error: {str(e)}")
                    await whatsapp_api.send_message(
                        phone_number,
                        "❌ Registration error. Please try again."
                    )
                    return
            
            # ADMIN COMMANDS - Check first before anything else
            if phone_number == "+27763514028":  # Your admin number
                if message_text.startswith("/reset"):
                    user.first_name = None
                    user.last_name = None
                    user.id_number = None
                    user.is_fica_compliant = False
                    user.status = UserStatus.PENDING_VERIFICATION
                    db.commit()
                    await whatsapp_api.send_message(phone_number, "✅ Account reset. Send 'Hi' to start fresh.")
                    return
                
                elif message_text.startswith("/complete"):
                    from datetime import date
                    user.first_name = "Test"
                    user.last_name = "User"
                    user.id_number = "9001011234567"
                    user.date_of_birth = date(1990, 1, 1)
                    user.is_fica_compliant = True
                    user.is_id_verified = True
                    user.status = UserStatus.ACTIVE
                    db.commit()
                    await whatsapp_api.send_message(phone_number, "✅ Account activated!")
                    return
            
            # Handle button responses (yes/no from confirmations + menu buttons)
            if message_text.lower() in ["yes", "no", "info", "airtime", "data", "electricity"]:
                if message_text.lower() == "yes":
                    # User confirmed - process transaction
                    await whatsapp_api.send_delay()
                    await whatsapp_api.send_message(
                        phone_number,
                        "✅ Processing your request...\n\n⚠️ Note: Your wallet balance is R0.00. Please top up to complete purchases."
                    )
                    return
                elif message_text.lower() == "no":
                    # User declined
                    await whatsapp_api.send_message(
                        phone_number,
                        "❌ Transaction cancelled. Let me know if you need anything else!"
                    )
                    return
                elif message_text.lower() == "info":
                    # User wants more info
                    await whatsapp_api.send_delay()
                    await whatsapp_api.send_message(
                        phone_number,
                        "ℹ️ *About Cyrax*\n\nI help you:\n• Buy airtime for any SA network\n• Get data bundles\n• Pay electricity bills\n\nSecure, fast, and easy! 🔐\n\nReady to register? Reply YES"
                    )
                    return
                elif message_text.lower() == "airtime":
                    # User clicked Buy Airtime button
                    await whatsapp_api.send_delay()
                    await whatsapp_api.send_message(
                        phone_number,
                        "📱 *Buy Airtime*\n\nTell me:\n• Phone number\n• Amount (R5 - R1000)\n• Network (optional)\n\nExample: \"Buy R50 MTN airtime for 0821234567\"\n\nOr send a photo of the number!"
                    )
                    return
                elif message_text.lower() == "data":
                    # User clicked Buy Data button
                    await whatsapp_api.send_delay()
                    await whatsapp_api.send_message(
                        phone_number,
                        "📊 *Buy Data*\n\nTell me:\n• Phone number\n• Data amount (1GB, 2GB, etc.)\n• Network\n\nExample: \"Buy 1GB Vodacom data for 0821234567\""
                    )
                    return
                elif message_text.lower() == "electricity":
                    # User clicked Recharge Meter button
                    await whatsapp_api.send_delay()
                    await whatsapp_api.send_message(
                        phone_number,
                        "⚡ *Recharge Meter*\n\nTell me:\n• Meter number (11 digits)\n• Amount (R10 - R5000)\n\nExample: \"Pay R100 electricity for meter 12345678901\"\n\nOr send a photo of your meter!"
                    )
                    return
            
        elif message_type == "audio":
            # Download and transcribe voice note
            message_text = await handle_voice_note(message)
            if not message_text:
                await whatsapp_api.send_message(
                    phone_number,
                    "Sorry, I couldn't understand your voice note. Please try again or send a text message. 🎤"
                )
                return
            
            # Process directly without echoing
            
        elif message_type == "image":
            # Download and process image with OCR
            # Get caption if provided
            caption = message.get("caption", message.get("text", ""))
            image_result = await handle_image(message, caption)
            
            if image_result and image_result.get("success"):
                extracted_data = image_result.get("data", {})
                confidence = extracted_data.get("confidence", 0)
                
                # Check if extraction was successful
                if confidence < 0.5:
                    await whatsapp_api.send_message(
                        phone_number,
                        "📸 I can see your image, but it's not clear enough. Please try:\n• Better lighting\n• Closer shot\n• Focus on the numbers"
                    )
                    return
                
                image_type = extracted_data.get("type", "unknown")
                amount = extracted_data.get("amount", "")  # Get amount from caption
                intent = extracted_data.get("intent", "")  # Get intent from caption
                
                # PHONE NUMBER DETECTED - Airtime Intent
                if image_type == "phone_number" or "phone_number" in extracted_data:
                    phone = extracted_data.get("phone_number", "")
                    provider = extracted_data.get("provider", "Unknown")
                    amount = extracted_data.get("amount", "")
                    
                    if phone:
                        # If amount already provided in caption, confirm with buttons
                        if amount and intent == "airtime":
                            await whatsapp_api.send_buttons(
                                phone_number,
                                f"📱 Confirm Airtime Purchase\n\n• Phone: {phone}\n• Network: {provider}\n• Amount: {amount}\n\nReady to proceed?",
                                [
                                    {"type": "reply", "reply": {"id": "yes", "title": "✅ Yes"}},
                                    {"type": "reply", "reply": {"id": "no", "title": "❌ No"}}
                                ]
                            )
                            return  # Don't process with AI
                        else:
                            # Amount missing - ask for it
                            await whatsapp_api.send_message(
                                phone_number,
                                f"📱 I found:\n• Phone: {phone}\n• Network: {provider if provider != 'Unknown' else 'Will detect automatically'}\n\n💰 How much airtime? (e.g., R10, R20, R50, R100)"
                            )
                            return  # Don't process with AI
                    else:
                        await whatsapp_api.send_message(
                            phone_number,
                            "📱 I see a phone number but couldn't read it clearly. Please type it or send a clearer photo."
                        )
                        return
                
                # METER NUMBER DETECTED - Electricity Intent
                elif image_type == "meter_number" or "meter_number" in extracted_data:
                    meter = extracted_data.get("meter_number", "")
                    provider = extracted_data.get("provider", "Eskom")
                    
                    if meter:
                        await whatsapp_api.send_message(
                            phone_number,
                            f"⚡ I found:\n• Meter: {meter}\n• Provider: {provider}\n\nHow much electricity would you like to buy? (e.g., R50, R100)"
                        )
                        # Set intent for electricity purchase
                        message_text = f"buy electricity for meter {meter}"
                    else:
                        await whatsapp_api.send_message(
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
                    
                    await whatsapp_api.send_message(phone_number, bill_msg)
                    # Set intent for bill payment
                    message_text = f"pay {provider} bill for account {account} amount {amount}"
                
                # UNKNOWN/UNCLEAR IMAGE
                else:
                    description = extracted_data.get("description", "an image")
                    await whatsapp_api.send_message(
                        phone_number,
                        f"📸 I see {description}, but I couldn't identify:\n• Phone number (for airtime)\n• Meter number (for electricity)\n• Utility bill (for payment)\n\nPlease try:\n✓ Close-up of the number\n✓ Good lighting\n✓ Clear focus"
                    )
                    # Still pass to AI for general processing
                    message_text = "help"
            
            else:
                await whatsapp_api.send_message(
                    phone_number,
                    "Sorry, I couldn't process your image. Please try again with a clearer photo! 📸"
                )
                return
        
        else:
            await whatsapp_api.send_message(
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
            "status": user.status.value,
            "is_verified": user.is_fica_compliant  # NEW: Include FICA status
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
        
        # STEP 1: Classify intent using rule-based classifier (no AI hallucination)
        from app.services.intent_classifier import classify_intent
        from app.services.response_validator import validate_ai_response
        
        # Handle button responses first
        if message_text.startswith("confirm_"):
            # User confirmed a typo suggestion
            action = message_text.replace("confirm_", "").replace("_", " ")
            # Re-classify with the confirmed intent
            message_text = action
        elif message_text == "cancel_typo":
            await whatsapp_api.send_message(
                phone_number,
                "Got it! What would you like to do?"
            )
            return
        
        classification = classify_intent(message_text, str(user.id), db)
        logger.info(f"Intent classified: {classification['intent']} (confidence: {classification['confidence']})")
        
        # STEP 2: If we have a direct handler and don't need AI, execute immediately
        if classification["handler"] and not classification["use_ai"]:
            handler_name = classification["handler"]
            
            if handler_name == "handle_typo_confirmation":
                # Ask user to confirm the typo correction
                suggested = classification.get("suggested_intent", "")
                await whatsapp_api.send_buttons(
                    phone_number,
                    f"Did you mean: *{suggested.title()}*?",
                    [
                        {"type": "reply", "reply": {"id": f"confirm_{suggested.replace(' ', '_')}", "title": "✅ Yes"}},
                        {"type": "reply", "reply": {"id": "cancel_typo", "title": "❌ No"}}
                    ]
                )
                return
            
            elif handler_name == "handle_save_beneficiary":
                await handle_save_beneficiary(phone_number, message_text, user.id, db)
                return
            
            elif handler_name == "handle_show_beneficiaries":
                await handle_show_beneficiaries(phone_number, user.id, db)
                return
            
            elif handler_name == "handle_delete_beneficiary":
                await handle_delete_beneficiary(phone_number, message_text, user.id, db)
                return
            
            elif handler_name == "handle_check_balance":
                await whatsapp_api.send_message(
                    phone_number,
                    f"💰 *Wallet Balance*\n\nCurrent balance: R{user.balance:.2f}"
                )
                return
            
            elif handler_name == "handle_account_details":
                # Show real account details from database
                details = f"""📋 *Account Details*\n\n"""
                details += f"Name: {user.full_name}\n"
                details += f"Phone: {user.phone_number}\n"
                details += f"Balance: R{user.balance:.2f}\n"
                details += f"Status: {user.status.value}\n"
                if user.is_fica_compliant:
                    details += f"✅ Verified\n"
                else:
                    details += f"⚠️ Not verified\n"
                # Don't show account number if not available
                if user.account_number:
                    details += f"Account: {user.account_number}\n"
                
                await whatsapp_api.send_message(phone_number, details)
                return
            
            elif handler_name == "send_menu":
                await send_menu(phone_number)
                return
            
            elif handler_name == "handle_beneficiary_transaction":
                await handle_beneficiary_transaction(
                    phone_number, 
                    message_text, 
                    user.id, 
                    classification["entities"],
                    db
                )
                return
            
            elif handler_name == "handle_buy_airtime":
                await handle_buy_airtime(
                    phone_number,
                    message_text,
                    user.id,
                    classification["entities"],
                    db
                )
                return
        
        # STEP 3: Only use AI if needed (incomplete requests or unclear intent)
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
        
        # STEP 4: Validate AI response (catch hallucinations)
        is_valid, final_response = validate_ai_response(ai_result["response"])
        if not is_valid:
            logger.warning(f"Hallucination caught and corrected")
        
        # Send validated response
        await whatsapp_api.send_message(phone_number, final_response)
        
        # Handle specific intents - only send menu for actual help requests
        if ai_result["intent"] == "help":
            await send_menu(phone_number)
        elif ai_result["intent"] == "greeting":
            # Only send menu if this is first message (no conversation history)
            if len(conversation_history) == 0:
                await send_menu(phone_number)
        
        # Handle beneficiary intents
        elif ai_result["intent"] == "save_beneficiary":
            await handle_save_beneficiary(phone_number, message_text, user.id, db)
        
        elif ai_result["intent"] == "show_beneficiaries":
            await handle_show_beneficiaries(phone_number, user.id, db)
        
        elif ai_result["intent"] == "delete_beneficiary":
            await handle_delete_beneficiary(phone_number, message_text, user.id, db)
        
    except Exception as e:
        logger.error(f"Message processing error: {str(e)}", exc_info=True)
        await whatsapp_api.send_message(
            phone_number,
            "Sorry, something went wrong. Please try again later. 😅"
        )


async def send_welcome_message_new_user(phone_number: str, name: str):
    """
    Send welcome message to new users with Flow button (Xara style).
    """
    welcome = f"""Hey {name}! 👋 I'm Cyrax, your AI assistant from Cyrax Technologies! I can handle transactions, schedule payments, analyze your spending, set up recurring transfers and spending limits, and even process voice notes and images! 😊

To keep your account secure, please lock your WhatsApp. 🔒

Ready to get started? Let's begin your onboarding! ✨"""
    
    # Send Flow for registration
    await whatsapp_api.send_flow(
        phone_number,
        welcome,
        "Complete Onboarding",
        "6916b0d4438bb928d88ac3a2"
    )


async def send_registration_instructions(phone_number: str):
    """
    Send registration form instructions (NO PIN).
    """
    instructions = """📋 *Account Setup*

Please send your details in this format:

REGISTER [FirstName] [LastName] [ID]

*Example:*
REGISTER Thabo Mokoena 9001011234567

*Requirements:*
• ✅ Your South African ID number (13 digits)
• ✅ Must be 18+ years old

*Your Info is Safe:*
🔐 ID is verified but never shared
🔐 FICA compliant
🔒 Use WhatsApp Chat Lock for security

Ready? Send your details now! 👆"""
    
    await whatsapp_api.send_message(phone_number, instructions)


async def handle_registration(phone_number: str, message_text: str, user: User, db: Session):
    """
    Handle user registration command (NO PIN).
    Format: REGISTER FirstName LastName IDNumber
    """
    try:
        # Parse registration data
        parts = message_text.strip().split()
        
        if len(parts) != 4:  # Changed from 5 to 4
            await whatsapp_api.send_message(
                phone_number,
                """❌ *Invalid Format*

Please use this format:
REGISTER [FirstName] [LastName] [ID]

*Example:*
REGISTER Thabo Mokoena 9001011234567

Try again! 👆"""
            )
            return
        
        _, first_name, last_name, id_number = parts  # No PIN
        
        # Create flow data format (NO PIN)
        flow_data = {
            "first_name": first_name,
            "last_name": last_name,
            "id_number": id_number
        }
        
        # Process registration
        success, message, updated_user = await onboarding_service.process_flow_response(
            phone_number,
            flow_data,
            db
        )
        
        # Send result
        await whatsapp_api.send_message(phone_number, message)
        
        # If successful, send menu
        if success:
            await send_menu(phone_number)
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        await whatsapp_api.send_message(
            phone_number,
            "❌ Something went wrong during registration. Please try again or contact support."
        )


async def handle_voice_note(message: dict) -> Optional[str]:
    """
    Download and transcribe voice note using Whisper.
    """
    try:
        # Get media_id (preferred) or media_url
        media_id = message.get("media_id")
        media_url = message.get("media_url")
        
        if not media_id and not media_url:
            logger.error("No media_id or media_url in voice message")
            return None
        
        # Download audio file
        audio_path = await download_media(
            media_id or media_url,
            message.get("message_id"),
            "ogg"  # WhatsApp sends .ogg format
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


async def handle_image(message: dict, caption: str = "") -> Optional[Dict]:
    """
    Download and process image with GPT-4 Vision (OCR).
    """
    try:
        # Get media_id (preferred) or media_url
        media_id = message.get("media_id")
        media_url = message.get("media_url")
        
        if not media_id and not media_url:
            logger.error("No media_id or media_url in image message")
            return None
        
        # Download image
        image_path = await download_media(
            media_id or media_url,
            message.get("message_id"),
            "jpg"  # Default to jpg
        )
        
        if not image_path:
            return None
        
        # Process with GPT-4 Vision - pass caption for context
        result = await ai_service.extract_text_from_image(str(image_path), caption)
        
        # Clean up file
        try:
            os.remove(image_path)
        except:
            pass
        
        return result
        
    except Exception as e:
        logger.error(f"Image handling error: {str(e)}")
        return None


async def download_media(media_url_or_id: str, message_id: str, extension: str) -> Optional[Path]:
    """
    Download media file from WhatsApp API.
    If media_url_or_id starts with digits, it's a media_id - fetch URL first.
    """
    try:
        # Check if this is a media_id (all digits) or a URL
        if media_url_or_id and not media_url_or_id.startswith("http"):
            # It's a media_id, fetch the URL
            logger.info(f"Fetching media URL for ID: {media_url_or_id}")
            media_url = await whatsapp_api.get_media_url(media_url_or_id)
            if not media_url:
                logger.error("Failed to get media URL from media_id")
                return None
        else:
            media_url = media_url_or_id
        
        if not media_url:
            return None
        
        # Download media with authentication
        from app.config import settings
        
        headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_API_KEY}"
        }
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                media_url,
                headers=headers,
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


async def send_menu(phone_number: str):
    """Send menu with quick reply buttons."""
    # Show typing
    await whatsapp_api.send_delay()
    
    await whatsapp_api.send_buttons(
        phone_number,
        "How can I help you today?",
        [
            {"type": "reply", "reply": {"id": "airtime", "title": "📱 Buy Airtime"}},
            {"type": "reply", "reply": {"id": "data", "title": "📊 Buy Data"}},
            {"type": "reply", "reply": {"id": "electricity", "title": "⚡ Recharge Meter"}}
        ]
    )


async def handle_save_beneficiary(phone_number: str, message: str, user_id: str, db: Session):
    """Handle 'save [nickname] [number]' command with flexible parsing"""
    from app.services.beneficiary_service import beneficiary_service
    from app.models.beneficiary import BeneficiaryType
    import re
    
    # Remove command words and clean up
    text = message.lower()
    text = text.replace("save beneficiary", "").replace("save", "").strip()
    text = text.replace(" number ", " ").replace(" meter ", " ").strip()
    
    # Split into parts
    parts = text.split()
    
    if len(parts) < 2:
        await whatsapp_api.send_message(
            phone_number,
            "Please use format:\n• save [name] [number]\n\nExamples:\n• save thabo 0821234567\n• save home meter 12345678901\n• save mom number 0827654321"
        )
        return
    
    # Last part is the number/account, rest is nickname
    value = parts[-1]
    nickname_parts = parts[:-1]
    nickname = " ".join(nickname_parts)
    
    # Auto-detect type
    is_meter = len(value) == 11 and value.isdigit()
    is_phone = bool(re.match(r'^(\+27|0)\d{9}$', value.replace("+", "")))
    
    if is_meter:
        btype = BeneficiaryType.METER
    elif is_phone:
        btype = BeneficiaryType.PHONE
    elif "water" in nickname:
        btype = BeneficiaryType.WATER
    elif "wifi" in nickname or "internet" in nickname:
        btype = BeneficiaryType.INTERNET
    elif "dstv" in nickname or "tv" in nickname:
        btype = BeneficiaryType.TV
    elif "municipal" in nickname or "council" in nickname:
        btype = BeneficiaryType.MUNICIPAL
    else:
        btype = BeneficiaryType.OTHER
    
    # Clean phone number if needed
    if is_phone and not value.startswith("+"):
        if value.startswith("0"):
            value = "+27" + value[1:]
    
    # Save
    success, msg, beneficiary = beneficiary_service.save_beneficiary(
        user_id=user_id,
        nickname=nickname,
        value=value,
        beneficiary_type=btype,
        network=None,
        db=db
    )
    
    await whatsapp_api.send_message(phone_number, msg)


async def handle_show_beneficiaries(phone_number: str, user_id: str, db: Session):
    """Show all saved beneficiaries"""
    from app.services.beneficiary_service import beneficiary_service
    
    beneficiaries = beneficiary_service.get_beneficiaries(user_id, None, db)
    message = beneficiary_service.format_beneficiary_list(beneficiaries)
    
    await whatsapp_api.send_message(phone_number, message)


async def handle_delete_beneficiary(phone_number: str, message: str, user_id: str, db: Session):
    """Handle 'delete [nickname]' command"""
    from app.services.beneficiary_service import beneficiary_service
    
    # Parse: "delete thabo" or "remove mom"
    nickname = message.lower().replace("delete ", "").replace("remove ", "").strip()
    
    if not nickname:
        await whatsapp_api.send_message(
            phone_number,
            "Please specify which beneficiary to delete.\n\nExample: delete thabo"
        )
        return
    
    success, msg = beneficiary_service.delete_beneficiary(user_id, nickname, db)
    await whatsapp_api.send_message(phone_number, msg)


async def handle_beneficiary_transaction(
    phone_number: str, 
    message: str, 
    user_id: str,
    entities: dict,
    db: Session
):
    """
    Handle transaction with saved beneficiary.
    Deterministic flow - no AI hallucination.
    """
    beneficiary = entities.get("beneficiary")
    amount = entities.get("amount")
    
    if not beneficiary:
        await whatsapp_api.send_message(phone_number, "Beneficiary not found.")
        return
    
    # Get user for balance check
    user = db.query(User).filter(User.id == user_id).first()
    
    # If amount missing, ask for it
    if not amount:
        await whatsapp_api.send_message(
            phone_number,
            f"How much for {beneficiary.nickname}?\n\nExample: R50, R100, R200"
        )
        return
    
    # Check balance
    if user.balance < amount:
        await whatsapp_api.send_message(
            phone_number,
            f"💰 Insufficient balance\n\nYou have: R{user.balance:.2f}\nYou need: R{amount:.2f}\n\nPlease top up your wallet."
        )
        return
    
    # Determine transaction type
    if beneficiary.beneficiary_type.value == "phone":
        transaction_type = "airtime"
        icon = "📱"
    elif beneficiary.beneficiary_type.value == "meter":
        transaction_type = "electricity"
        icon = "⚡"
    else:
        transaction_type = "utility"
        icon = "💳"
    
    # Send confirmation with buttons
    await whatsapp_api.send_buttons(
        phone_number,
        f"{icon} *Confirm Purchase*\n\n• For: {beneficiary.nickname}\n• Account: {beneficiary.value}\n• Amount: R{amount:.2f}\n• Type: {transaction_type.title()}\n\nProceed?",
        [
            {"type": "reply", "reply": {"id": "yes_confirm", "title": "✅ Yes"}},
            {"type": "reply", "reply": {"id": "no", "title": "❌ No"}}
        ]
    )


async def handle_buy_airtime(
    phone_number: str,
    message_text: str,
    user_id: str,
    entities: dict,
    db: Session
):
    """
    Handle airtime purchase - deterministic, step-by-step.
    NO AI HALLUCINATION.
    """
    from app.services.intent_classifier import extract_amount, extract_phone, extract_network
    
    # Extract entities from message
    amount = entities.get("amount") or extract_amount(message_text)
    phone = entities.get("phone") or extract_phone(message_text)
    network = entities.get("network") or extract_network(message_text)
    
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    
    # Step 1: Check what's missing
    missing = []
    if not network:
        missing.append("network")
    if not amount:
        missing.append("amount")
    if not phone:
        missing.append("phone number")
    
    # If anything missing, ask for it
    if missing:
        if "network" in missing and "amount" in missing:
            await whatsapp_api.send_message(
                phone_number,
                "Which network and how much?\n\nExample: R20 MTN"
            )
        elif "phone number" in missing:
            await whatsapp_api.send_message(
                phone_number,
                f"For which number?\n\nExample: 0821234567"
            )
        elif "amount" in missing:
            await whatsapp_api.send_message(
                phone_number,
                f"How much {network} airtime?\n\nExample: R20, R50, R100"
            )
        elif "network" in missing:
            await whatsapp_api.send_buttons(
                phone_number,
                "Which network?",
                [
                    {"type": "reply", "reply": {"id": "mtn", "title": "MTN"}},
                    {"type": "reply", "reply": {"id": "vodacom", "title": "Vodacom"}},
                    {"type": "reply", "reply": {"id": "cell_c", "title": "Cell C"}}
                ]
            )
        return
    
    # Step 2: All info present - check balance
    if user.balance < amount:
        await whatsapp_api.send_message(
            phone_number,
            f"⚠️ *Insufficient Balance*\n\nYou have: R{user.balance:.2f}\nYou need: R{amount:.2f}\n\nPlease top up to continue."
        )
        return
    
    # Step 3: Send confirmation buttons
    await whatsapp_api.send_buttons(
        phone_number,
        f"📱 *Confirm Airtime Purchase*\n\n• Network: {network.title()}\n• Phone: {phone}\n• Amount: R{amount:.2f}\n\nProceed?",
        [
            {"type": "reply", "reply": {"id": f"confirm_airtime_{network}_{phone}_{amount}", "title": "✅ Confirm"}},
            {"type": "reply", "reply": {"id": "cancel", "title": "❌ Cancel"}}
        ]
    )
