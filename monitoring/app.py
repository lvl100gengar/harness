from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import asyncio
from datetime import datetime

from monitoring.config import Settings
from monitoring.database import DatabaseService, TransactionService, MetricsService
from monitoring.models import MockDataGenerator, Transaction, DatabaseStatus, TransactionStatus, ProcessingMetrics

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="File Transfer Monitor")

# Mount static files
static_path = Path(__file__).parent / "static"
templates_path = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
templates = Jinja2Templates(directory=str(templates_path))

# Global metrics service instance
metrics_service: Optional[MetricsService] = None

# Settings dependency
async def get_settings() -> Settings:
    return Settings()

# Services dependencies
async def get_transaction_service(settings: Settings = Depends(get_settings)) -> TransactionService:
    ingress_db = DatabaseService(settings.ingress_db, "ingress")
    egress_db = DatabaseService(settings.egress_db, "egress")
    
    if not settings.mock_mode:
        try:
            await ingress_db.connect()
            await egress_db.connect()
        except Exception as e:
            logger.error(f"Failed to connect to databases: {e}")
            # Don't raise here - we'll show the error in the UI
    
    return TransactionService(ingress_db, egress_db)

async def get_mock_generator(settings: Settings = Depends(get_settings)) -> Optional[MockDataGenerator]:
    if settings.mock_mode:
        return MockDataGenerator(settings.mock_data_rate)
    return None

async def get_metrics_service(
    transaction_service: TransactionService = Depends(get_transaction_service)
) -> MetricsService:
    global metrics_service
    if metrics_service is None:
        metrics_service = MetricsService(transaction_service)
    return metrics_service

async def background_metrics_update():
    """Background task to update metrics periodically"""
    global metrics_service
    while True:
        try:
            if metrics_service:
                await metrics_service.update_metrics()
            await asyncio.sleep(5)  # Update every 5 seconds
        except Exception as e:
            logger.error(f"Error in background metrics update: {e}")
            await asyncio.sleep(5)  # Still wait before retrying

# Routes
@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    settings: Settings = Depends(get_settings)
):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": settings
        }
    )

@app.get("/api/status")
async def get_status(
    service: TransactionService = Depends(get_transaction_service)
) -> Tuple[DatabaseStatus, DatabaseStatus]:
    return service.get_database_status()

@app.get("/api/transactions")
async def get_transactions(
    limit: int = 100,
    service: TransactionService = Depends(get_transaction_service),
    mock_gen: Optional[MockDataGenerator] = Depends(get_mock_generator),
    settings: Settings = Depends(get_settings)
) -> Dict[str, List]:
    if settings.mock_mode and mock_gen:
        # Generate mock data with some in-transit transactions
        all_transactions = await mock_gen.generate_mock_data(limit)
        
        # Split into completed and in-transit
        completed = []
        in_transit = []
        
        for t in all_transactions:
            if t.status == TransactionStatus.TIMEOUT:
                # Convert timeout transactions to in-transit for mock data
                in_transit.append({
                    "uuid": t.uuid,
                    "username": t.username,
                    "filename": t.filename,
                    "file_size": t.file_size,
                    "start_time": t.start_time,
                    "duration_so_far": (datetime.now() - t.start_time).total_seconds(),
                    "status": "IN_TRANSIT"
                })
            else:
                completed.append({
                    "uuid": t.uuid,
                    "username": t.username,
                    "filename": t.filename,
                    "file_size": t.file_size,
                    "start_time": t.start_time,
                    "end_time": t.end_time,
                    "status": t.status,
                    "duration": (t.end_time - t.start_time).total_seconds() if t.end_time else None
                })
        
        # Sort by time (most recent first)
        completed.sort(key=lambda x: x["end_time"] or datetime.min, reverse=True)
        in_transit.sort(key=lambda x: x["start_time"], reverse=True)
        
        return {
            "completed": completed[:limit],
            "in_transit": in_transit
        }
    else:
        # Get real data
        try:
            return await service.get_all_transactions(limit)
        except Exception as e:
            logger.error(f"Failed to fetch transactions: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metrics")
async def get_metrics(
    metrics_service: MetricsService = Depends(get_metrics_service)
) -> Dict:
    """Get current processing metrics"""
    return {
        "metrics": metrics_service.metrics,
        "last_update": metrics_service.last_update
    }

# Startup and shutdown events
@app.on_event("startup")
async def startup():
    logger.info("Starting up File Transfer Monitor")
    # Start background metrics update task
    asyncio.create_task(background_metrics_update())

@app.on_event("shutdown")
async def shutdown():
    logger.info("Shutting down File Transfer Monitor") 