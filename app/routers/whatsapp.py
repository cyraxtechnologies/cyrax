"""
WhatsApp Router
Handles all WhatsApp webhook callbacks for Cyrax via Twilio
"""
from fastapi import APIRouter, Request, Depends, BackgroundTasks
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
import logging
from datetime import datetime

from app.database import get_db
from app.models.user import User, UserStatus
from app.models.conversation import Conversation
from app.services.twilio_service import twilio_whatsapp
from app.services.ai_service import AIService
from app.services.transaction_service import transaction_service
from app.services.security_service import security_service

logger = logging.getLogger(__name__)

router = APIRouter()

# User session storage (in production, use Redis)
user_sessions = {}


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
    """Process incoming WhatsApp message - This is where Cyrax magic happens!"""
    try:
        phone_number = message.get("from_phone")
        message_id = message.get("message_id")
        message_type = message.get("type")
        
        # Get or create user
        user = db.query(User).filter(User.phone_number == phone_number).first()
        if not user:
            user = User(
                phone_number=phone_number,
                whatsapp_name=message.get("from_name"),
                status=UserStatus.PENDING_VERIFICATION
            )
            db.add(user)
            db.commit()
            
            await send_welcome_message(phone_number, message.get("from_name"))
            return
        
        user.last_active_at = datetime.utcnow()
        db.commit()
        
        # Extract message text
        if message_type == "text":
            text = message.get("text", "")
        else:
            await twilio_whatsapp.send_message(
                phone_number,
                f"Sorry, I only support text messages for now. Please send a text message."
            )
            return
        
        # Sanitize input
        text = security_service.sanitize_input(text)
        
        # Log conversation
        conversation = Conversation(
            user_id=user.id,
            phone_number=phone_number,
            message_id=message_id,
            message_type=message_type,
            direction="inbound",
            message_text=text
        )
        db.add(conversation)
        db.commit()
        
        # Check user session state
        session = user_sessions.get(phone_number, {})
        
        if session.get("state") == "awaiting_pin":
            await handle_pin_input(user, text, session, phone_number, db)
            return
        
        elif session.get("state") == "awaiting_confirmation":
            await handle_confirmation(user, text, session, phone_number, db)
            return
        
        elif session.get("state") == "setting_pin":
            await handle_pin_setup(user, text, phone_number, db)
            return
        
        # Regular message processing
        await handle_regular_message(user, text, phone_number, db)
        
    except Exception as e:
        logger.error(f"Message processing error: {str(e)}")
        try:
            await twilio_whatsapp.send_message(
                phone_number,
                "Sorry, something went wrong. Please try again."
            )
        except:
            pass


async def send_welcome_message(phone_number: str, name: str):
    """Send welcome message to new users."""
    message = f"""👋 Hi {name or 'there'}! Welcome to Cyrax!

I'm your AI financial assistant. I can help you:
💸 Send money
📱 Buy airtime & data
⚡ Pay for electricity
💰 Check your balance

To get started, please set up your transaction PIN.
Reply with a 4-6 digit PIN (e.g., 5678)

Don't use common PINs like 0000 or 1234!"""
    
    await twilio_whatsapp.send_message(phone_number, message)
    user_sessions[phone_number] = {"state": "setting_pin", "step": 1}


async def handle_pin_setup(user: User, text: str, phone_number: str, db: Session):
    """Handle PIN setup flow."""
    success, message = await security_service.set_user_pin(db, str(user.id), text)
    
    if success:
        await twilio_whatsapp.send_message(
            phone_number,
            f"✅ {message}\n\nYou're all set! Try:\n- Check balance\n- Send R10 to John"
        )
        user_sessions.pop(phone_number, None)
    else:
        await twilio_whatsapp.send_message(
            phone_number,
            f"❌ {message}\n\nTry again with a 4-6 digit PIN."
        )


async def handle_regular_message(user: User, text: str, phone_number: str, db: Session):
    """Handle regular conversational messages with AI."""
    
    balance_info = transaction_service.get_user_balance(db, str(user.id))
    user_context = {
        "name": user.full_name,
        "phone": user.phone_number,
        "balance": balance_info.get("balance", 0) if balance_info else 0,
        "daily_limit_remaining": balance_info.get("daily_limit_remaining", 0) if balance_info else 0,
        "is_fica_compliant": user.is_fica_compliant
    }
    
    history = db.query(Conversation).filter(
        Conversation.phone_number == phone_number
    ).order_by(Conversation.created_at.desc()).limit(5).all()
    
    conversation_history = []
    for conv in reversed(history):
        if conv.direction == "inbound" and conv.message_text:
            conversation_history.append({"role": "user", "content": conv.message_text})
        if conv.ai_response:
            conversation_history.append({"role": "assistant", "content": conv.ai_response})
    
    ai_result = await AIService.process_message(
        message=text,
        user_context=user_context,
        conversation_history=conversation_history
    )
    
    conversation = db.query(Conversation).filter(
        Conversation.phone_number == phone_number
    ).order_by(Conversation.created_at.desc()).first()
    
    if conversation:
        conversation.ai_response = ai_result["response"]
        conversation.intent_detected = ai_result["intent"]
        conversation.entities_extracted = ai_result["entities"]
        conversation.confidence_score = ai_result["confidence"]
        conversation.is_processed = True
        db.commit()
    
    intent = ai_result["intent"]
    
    if intent == "check_balance":
        await handle_balance_check(user, phone_number, db)
    
    elif intent == "transaction_history":
        await handle_transaction_history(user, phone_number, db)
    
    elif intent in ["send_money", "airtime_purchase", "electricity_purchase"]:
        if not user.is_fica_compliant:
            # For testing, enable FICA
            user.is_fica_compliant = True
            db.commit()
        
        confirmation_msg = AIService.generate_confirmation_message(
            intent,
            ai_result["entities"]
        )
        
        user_sessions[phone_number] = {
            "state": "awaiting_confirmation",
            "intent": intent,
            "entities": ai_result["entities"]
        }
        
        await twilio_whatsapp.send_message(phone_number, confirmation_msg)
    
    else:
        await twilio_whatsapp.send_message(phone_number, ai_result["response"])


async def handle_confirmation(user: User, text: str, session: dict, phone_number: str, db: Session):
    """Handle transaction confirmation (YES/NO)."""
    text_lower = text.lower().strip()
    
    if text_lower in ["yes", "y", "confirm", "ok", "proceed"]:
        user_sessions[phone_number] = {
            "state": "awaiting_pin",
            "intent": session["intent"],
            "entities": session["entities"]
        }
        
        await twilio_whatsapp.send_message(
            phone_number,
            "🔐 Please enter your transaction PIN to proceed:"
        )
    
    elif text_lower in ["no", "n", "cancel", "stop"]:
        user_sessions.pop(phone_number, None)
        await twilio_whatsapp.send_message(
            phone_number,
            "❌ Transaction cancelled. How else can I help you?"
        )
    
    else:
        await twilio_whatsapp.send_message(
            phone_number,
            "Please reply 'YES' to confirm or 'NO' to cancel."
        )


async def handle_pin_input(user: User, pin: str, session: dict, phone_number: str, db: Session):
    """Handle PIN verification and process transaction."""
    
    is_valid, message = await security_service.verify_user_pin(db, str(user.id), pin)
    
    if not is_valid:
        await twilio_whatsapp.send_message(phone_number, f"❌ {message}")
        if "locked" in message.lower():
            user_sessions.pop(phone_number, None)
        return
    
    intent = session["intent"]
    entities = session["entities"]
    
    user_sessions.pop(phone_number, None)
    
    await twilio_whatsapp.send_message(phone_number, "⏳ Processing...")
    
    try:
        if intent == "send_money":
            success, msg, txn = await transaction_service.send_money(
                db=db,
                sender_id=str(user.id),
                recipient_phone=entities.get("recipient", phone_number),
                amount=float(entities.get("amount", 0)),
                description=entities.get("recipient_name")
            )
        
        elif intent == "airtime_purchase":
            success, msg, txn = await transaction_service.buy_airtime(
                db=db,
                user_id=str(user.id),
                phone_number=entities.get("phone_number", user.phone_number),
                amount=float(entities.get("amount", 0)),
                provider=entities.get("provider", "MTN")
            )
        
        else:
            success = False
            msg = "Transaction type not yet supported"
        
        if success:
            await twilio_whatsapp.send_message(
                phone_number,
                f"✅ {msg}\n\nRef: {txn.payment_reference if txn else ''}\n\nNew balance: R{user.balance:.2f}"
            )
        else:
            await twilio_whatsapp.send_message(phone_number, f"❌ {msg}")
    
    except Exception as e:
        logger.error(f"Transaction processing error: {str(e)}")
        await twilio_whatsapp.send_message(
            phone_number,
            "❌ Transaction failed. Please try again."
        )


async def handle_balance_check(user: User, phone_number: str, db: Session):
    """Send balance information."""
    balance_info = transaction_service.get_user_balance(db, str(user.id))
    
    if balance_info:
        message = f"""💰 Account Balance

Available: R{balance_info['balance']:.2f}

📊 Daily Limits:
Remaining: R{balance_info['daily_limit_remaining']:.2f}

📈 Monthly Limits:
Remaining: R{balance_info['monthly_limit_remaining']:.2f}"""
        
        await twilio_whatsapp.send_message(phone_number, message)
    else:
        await twilio_whatsapp.send_message(
            phone_number,
            "Sorry, I couldn't retrieve your balance. Please try again."
        )


async def handle_transaction_history(user: User, phone_number: str, db: Session):
    """Send recent transaction history."""
    transactions = transaction_service.get_transaction_history(db, str(user.id), limit=5)
    
    if not transactions:
        await twilio_whatsapp.send_message(
            phone_number,
            "You have no recent transactions."
        )
        return
    
    message = "📋 Recent Transactions:\n\n"
    
    for txn in transactions:
        message += f"• {txn['type'].replace('_', ' ').title()}\n"
        message += f"  Amount: R{txn['amount']:.2f}\n"
        message += f"  Status: {txn['status'].title()}\n"
        message += f"  Date: {txn['created_at'][:10]}\n\n"
    
    await twilio_whatsapp.send_message(phone_number, message)