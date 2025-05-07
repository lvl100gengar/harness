import aiomysql
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict
import logging
from monitoring.models import Transaction, DatabaseStatus, TransactionStatus, ProcessingMetrics
from monitoring.config import DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseService:
    def __init__(self, db_config: DatabaseConfig, name: str):
        self.config = db_config
        self.name = name
        self.pool = None
        self.status = DatabaseStatus(
            connected=False,
            host=db_config.host
        )

    async def connect(self):
        try:
            if self.pool is None:
                self.pool = await aiomysql.create_pool(
                    host=self.config.host,
                    port=self.config.port,
                    user=self.config.username,
                    password=self.config.password,
                    db=self.config.database,
                    ssl=self.config.ssl,
                    autocommit=True
                )
            self.status.connected = True
            self.status.last_successful_connection = datetime.now()
            self.status.error_message = None
            logger.info(f"Successfully connected to {self.name} database")
        except Exception as e:
            self.status.connected = False
            self.status.error_message = str(e)
            logger.error(f"Failed to connect to {self.name} database: {e}")
            raise

    async def disconnect(self):
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None
            self.status.connected = False

    async def get_recent_transactions(self, limit: int = 100) -> List[Transaction]:
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                query = """
                SELECT uuid, username, filename, file_size, startTime, endTime, status
                FROM file_tracking
                ORDER BY startTime DESC
                LIMIT %s
                """
                await cur.execute(query, (limit,))
                rows = await cur.fetchall()

                return [
                    Transaction(
                        uuid=row[0],
                        username=row[1],
                        filename=row[2],
                        file_size=row[3] if row[3] is not None else 0,
                        start_time=row[4],
                        end_time=row[5],
                        status=TransactionStatus(row[6])
                    )
                    for row in rows
                ]

    async def get_transactions_in_timespan(
        self, 
        start_time: datetime, 
        end_time: Optional[datetime] = None
    ) -> List[Transaction]:
        if not end_time:
            end_time = datetime.now()

        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                query = """
                SELECT uuid, username, filename, file_size, startTime, endTime, status
                FROM file_tracking
                WHERE startTime BETWEEN %s AND %s
                ORDER BY startTime DESC
                """
                await cur.execute(query, (start_time, end_time))
                rows = await cur.fetchall()

                return [
                    Transaction(
                        uuid=row[0],
                        username=row[1],
                        filename=row[2],
                        file_size=row[3] if row[3] is not None else 0,
                        start_time=row[4],
                        end_time=row[5],
                        status=TransactionStatus(row[6])
                    )
                    for row in rows
                ]


class TransactionService:
    def __init__(self, ingress_db: DatabaseService, egress_db: DatabaseService):
        self.ingress_db = ingress_db
        self.egress_db = egress_db

    async def get_all_transactions(self, limit: int = 100) -> Dict[str, List]:
        ingress_trans = await self.ingress_db.get_recent_transactions(limit * 2)  # Get more to account for in-transit
        egress_trans = await self.egress_db.get_recent_transactions(limit * 2)

        # Create lookup dictionary for egress transactions
        egress_dict = {t.uuid: t for t in egress_trans}

        # Separate completed and in-transit transactions
        completed = []
        in_transit = []

        for ingress_t in ingress_trans:
            if ingress_t.uuid in egress_dict:
                egress_t = egress_dict[ingress_t.uuid]
                completed.append({
                    "uuid": ingress_t.uuid,
                    "username": ingress_t.username,
                    "filename": ingress_t.filename,
                    "file_size": ingress_t.file_size,
                    "start_time": ingress_t.start_time,
                    "end_time": egress_t.end_time,
                    "status": egress_t.status,
                    "duration": (egress_t.end_time - ingress_t.start_time).total_seconds() 
                    if egress_t.end_time else None
                })
            else:
                in_transit.append({
                    "uuid": ingress_t.uuid,
                    "username": ingress_t.username,
                    "filename": ingress_t.filename,
                    "file_size": ingress_t.file_size,
                    "start_time": ingress_t.start_time,
                    "duration_so_far": (datetime.now() - ingress_t.start_time).total_seconds(),
                    "status": "IN_TRANSIT"
                })

        # Sort both lists by time (most recent first)
        completed.sort(key=lambda x: x["end_time"] or datetime.min, reverse=True)
        in_transit.sort(key=lambda x: x["start_time"], reverse=True)

        # Limit the completed transactions after sorting
        return {
            "completed": completed[:limit],
            "in_transit": in_transit
        }

    def get_database_status(self) -> Tuple[DatabaseStatus, DatabaseStatus]:
        return self.ingress_db.status, self.egress_db.status 


class MetricsService:
    def __init__(self, transaction_service: TransactionService):
        self.transaction_service = transaction_service
        self._last_update = datetime.now()
        self._metrics = ProcessingMetrics()

    async def update_metrics(self) -> ProcessingMetrics:
        """Calculate and update metrics based on current transactions"""
        try:
            transactions = await self.transaction_service.get_all_transactions(1000)
            now = datetime.now()
            window = timedelta(minutes=5)  # Use 5-minute window for rate calculations
            
            # Split transactions into completed and in-transit
            completed = transactions.get("completed", [])
            in_transit = transactions.get("in_transit", [])
            
            # Calculate in-transit metrics
            self._metrics.files_in_transit = len(in_transit)
            self._metrics.bytes_in_transit = sum(t.get("file_size", 0) for t in in_transit)
            
            # Calculate completed metrics within window
            recent_completed = [
                t for t in completed 
                if t.get("end_time") and isinstance(t["end_time"], datetime) and 
                now - t["end_time"] <= window
            ]
            
            if recent_completed:
                # Calculate files per minute
                window_start = min(t["end_time"] for t in recent_completed)
                time_span = max((now - window_start).total_seconds() / 60, 0.1)  # Avoid division by zero
                self._metrics.files_per_minute = len(recent_completed) / time_span
                
                # Calculate bytes per second
                total_bytes = sum(t.get("file_size", 0) for t in recent_completed)
                self._metrics.bytes_per_second = total_bytes / (time_span * 60)
                
                # Calculate average processing time
                processing_times = [
                    (t["end_time"] - t["start_time"]).total_seconds()
                    for t in recent_completed
                    if t.get("end_time") and t.get("start_time")
                ]
                if processing_times:
                    self._metrics.avg_processing_time = sum(processing_times) / len(processing_times)
            
            # Update totals
            self._metrics.total_files_processed = len(completed)
            self._metrics.total_bytes_processed = sum(t.get("file_size", 0) for t in completed)
            
            self._last_update = now
            return self._metrics
            
        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")
            logger.exception(e)  # Log full traceback for debugging
            return self._metrics

    @property
    def metrics(self) -> ProcessingMetrics:
        """Get the current metrics"""
        return self._metrics

    @property
    def last_update(self) -> datetime:
        """Get the timestamp of the last metrics update"""
        return self._last_update 