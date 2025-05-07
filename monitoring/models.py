from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
import uuid
import random
import asyncio


class TransactionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class Transaction(BaseModel):
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    filename: str
    file_size: int  # Size in bytes
    start_time: datetime
    end_time: Optional[datetime] = None
    status: TransactionStatus


class DatabaseStatus(BaseModel):
    connected: bool
    host: str
    last_successful_connection: Optional[datetime] = None
    error_message: Optional[str] = None


class ProcessingMetrics(BaseModel):
    files_in_transit: int = 0
    bytes_in_transit: int = 0
    files_per_minute: float = 0
    bytes_per_second: float = 0
    avg_processing_time: float = 0  # seconds
    total_files_processed: int = 0
    total_bytes_processed: int = 0


class MockDataGenerator:
    def __init__(self, rate_per_minute: int = 10):
        self.rate_per_minute = rate_per_minute
        self.usernames = ["user1", "user2", "user3", "sftp_user", "http_user"]
        self.file_prefixes = ["data", "report", "backup", "log", "export"]
        self.file_extensions = [".txt", ".csv", ".json", ".xml", ".dat"]
        self.file_sizes = [
            1024,  # 1KB
            1024 * 10,  # 10KB
            1024 * 100,  # 100KB
            1024 * 1024,  # 1MB
            1024 * 1024 * 10,  # 10MB
        ]

    def generate_transaction(self) -> Transaction:
        start_time = datetime.now() - timedelta(minutes=random.randint(0, 30))
        duration = timedelta(seconds=random.randint(1, 300))
        status = random.choices(
            list(TransactionStatus),
            weights=[0.8, 0.15, 0.05],
            k=1
        )[0]

        return Transaction(
            username=random.choice(self.usernames),
            filename=f"{random.choice(self.file_prefixes)}_{uuid.uuid4().hex[:8]}{random.choice(self.file_extensions)}",
            file_size=random.choice(self.file_sizes),
            start_time=start_time,
            end_time=start_time + duration if status != TransactionStatus.TIMEOUT else None,
            status=status
        )

    async def generate_mock_data(self, num_transactions: int) -> List[Transaction]:
        return [self.generate_transaction() for _ in range(num_transactions)] 