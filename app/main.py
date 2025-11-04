"""
Main FastAPI Application - Cyrax Entry Point
"""
from fastapi import FastAPI, Request, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session
import logging
from typing import Optional
import asyncio

from app.config import settings, LOGGING_CONFIG
from app.database import get_db, init_db
from app.routers import whatsapp, admin

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered financial assistant on WhatsApp for South Africa",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(whatsapp.router, prefix="/webhook", tags=["WhatsApp"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    
    try:
        init_db()
        logger.info("Database initialized successfully")
        
        import os
        os.makedirs("logs", exist_ok=True)
        os.makedirs("media", exist_ok=True)
        
        logger.info("Cyrax startup complete!")
        
    except Exception as e:
        logger.error(f"Startup error: {str(e)}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down Cyrax...")


@app.get("/", response_class=PlainTextResponse)
async def root():
    """Health check endpoint."""
    return f"{settings.APP_NAME} v{settings.APP_VERSION} - Running"


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Detailed health check."""
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
