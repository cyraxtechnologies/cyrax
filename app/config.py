"""
Configuration Management
Handles all environment variables and application settings
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All sensitive data should be in .env file, never hardcoded.
    """
    
    # Application
    APP_NAME: str = "Cyrax"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # WhatsApp Business API (Meta/Facebook)
    WHATSAPP_API_URL: str = "https://graph.facebook.com/v18.0"
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_WEBHOOK_SECRET: str = ""

    # Twilio WhatsApp (Alternative to Meta - easier to set up)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""
    
    # AI Services - OpenAI
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"  # Updated to faster, cheaper model
    OPENAI_VISION_MODEL: str = "gpt-4o"  # For image recognition (NEW!)
    OPENAI_WHISPER_MODEL: str = "whisper-1"  # For voice transcription (NEW!)
    
    # Feature Flags (NEW!)
    ENABLE_VOICE_NOTES: bool = True
    ENABLE_IMAGE_RECOGNITION: bool = True
    
    # Payment Gateway (PayStack for South Africa)
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""
    PAYSTACK_WEBHOOK_SECRET: str = ""
    PAYSTACK_BASE_URL: str = "https://api.paystack.co"
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    PIN_ENCRYPTION_KEY: str
    
    # Transaction Limits (in ZAR)
    MAX_TRANSACTION_AMOUNT: float = 5000.00
    DAILY_TRANSACTION_LIMIT: float = 25000.00
    MIN_TRANSACTION_AMOUNT: float = 1.00
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 30
    
    # Monitoring
    SENTRY_DSN: Optional[str] = None
    
    # File Upload (NEW!)
    MAX_FILE_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: list = ["image/jpeg", "image/png", "image/webp"]
    ALLOWED_AUDIO_TYPES: list = ["audio/ogg", "audio/mpeg", "audio/mp4"]
    MEDIA_DIR: str = "media"  # Directory for temporary media storage
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    
    # FICA Compliance
    REQUIRE_ID_VERIFICATION: bool = True
    REQUIRE_PROOF_OF_RESIDENCE: bool = True
    MIN_AGE: int = 18
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        # Allow extra fields (for backward compatibility)
        extra = "ignore"  # This prevents the validation error!


# Singleton instance
settings = Settings()


# Logging configuration
import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "json",
            "filename": "logs/cyrax.log",
            "maxBytes": 10485760,
            "backupCount": 10,
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
    },
    "loggers": {
        "uvicorn": {"level": "INFO"},
        "sqlalchemy.engine": {"level": "WARNING"},
    },
}


# Constants
class MessageType:
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


class TransactionStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class TransactionType:
    SEND_MONEY = "send_money"
    RECEIVE_MONEY = "receive_money"
    BILL_PAYMENT = "bill_payment"
    AIRTIME_PURCHASE = "airtime_purchase"
    DATA_PURCHASE = "data_purchase"
    ELECTRICITY_PURCHASE = "electricity_purchase"
    WITHDRAWAL = "withdrawal"


class UserStatus:
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked" 