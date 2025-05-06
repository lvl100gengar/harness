"""Job execution module for file transfers."""

import asyncio
import logging
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional

import aiohttp
import asyncssh
import aiofiles

from .config import HTTPJobConfig, SFTPJobConfig, parse_rate


class Job(ABC):
    """Base class for transfer jobs."""

    def __init__(self, name: str, directory: str, initial_rate: str, target_rate: str,
                 username: str, ramp_rate: Optional[str] = None):
        self.name = name
        self.directory = directory
        self.username = username
        self.logger = logging.getLogger(f"job.{name}")

        # Parse rates
        self.initial_files_per_second = parse_rate(initial_rate)
        self.target_files_per_second = parse_rate(target_rate)
        self.ramp_files_per_second = parse_rate(ramp_rate) if ramp_rate else 0

        # Validate rates
        if self.initial_files_per_second > self.target_files_per_second:
            raise ValueError(
                f"Initial rate ({initial_rate}) cannot be higher than "
                f"target rate ({target_rate})"
            )
        
        # Start with initial rate
        self.current_files_per_second = self.initial_files_per_second
        self.interval = self._calculate_interval()
        self.last_ramp_time = None

    def _calculate_interval(self) -> float:
        """Calculate the interval between file sends based on current rate."""
        return 1.0 / self.current_files_per_second if self.current_files_per_second > 0 else float('inf')

    def _update_rate(self) -> None:
        """Update the current rate based on ramp configuration."""
        if not self.ramp_files_per_second or not self.last_ramp_time:
            return

        # Calculate how much time has passed since last ramp
        time_passed = (datetime.now() - self.last_ramp_time).total_seconds()
        
        # Calculate how much to increase the rate
        rate_increase = self.ramp_files_per_second * time_passed
        new_rate = min(
            self.current_files_per_second + rate_increase,
            self.target_files_per_second
        )
        
        if new_rate != self.current_files_per_second:
            self.current_files_per_second = new_rate
            self.interval = self._calculate_interval()
            self.logger.info(
                f"Ramped transfer rate to {self.current_files_per_second:.2f} files/second "
                f"(interval: {self.interval:.2f}s)"
            )

        self.last_ramp_time = datetime.now()

    @abstractmethod
    async def send_file(self, filepath: str, transaction_id: str) -> bool:
        """Send a single file."""
        pass

    async def run(self):
        """Run the job continuously."""
        self.logger.info(f"Starting job {self.name} for user {self.username}")
        
        if self.ramp_files_per_second:
            self.logger.info(
                f"Rate ramping enabled: Starting at {self.current_files_per_second:.2f} files/second, "
                f"increasing by {self.ramp_files_per_second:.2f} files/second, "
                f"up to {self.target_files_per_second:.2f} files/second"
            )
            self.last_ramp_time = datetime.now()
        else:
            self.logger.info(
                f"Fixed rate: {self.current_files_per_second:.2f} files/second "
                f"(interval: {self.interval:.2f}s)"
            )
        
        while True:
            try:
                # Update rate if ramping is enabled
                self._update_rate()

                files = os.listdir(self.directory)
                if not files:
                    await asyncio.sleep(1)
                    continue

                for filename in files:
                    filepath = os.path.join(self.directory, filename)
                    if not os.path.isfile(filepath):
                        continue

                    transaction_id = str(uuid.uuid4())
                    start_time = datetime.now()

                    try:
                        success = await self.send_file(filepath, transaction_id)
                        if success:
                            os.remove(filepath)  # Remove file after successful transfer
                    except Exception as e:
                        self.logger.error(f"Error sending file {filename}: {str(e)}")
                        success = False

                    duration = (datetime.now() - start_time).total_seconds()
                    self.logger.info(
                        f"File {filename} transfer {'succeeded' if success else 'failed'} "
                        f"(took {duration:.2f}s)"
                    )

                    # Wait for the next interval, accounting for transfer duration
                    await asyncio.sleep(max(0, self.interval - duration))

            except Exception as e:
                self.logger.error(f"Job error: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying


class HTTPJob(Job):
    """HTTP file transfer job."""

    def __init__(self, name: str, config: HTTPJobConfig):
        super().__init__(
            name=name,
            directory=config.directory,
            initial_rate=config.initial_rate,
            target_rate=config.target_rate,
            username=config.username,
            ramp_rate=config.ramp_rate
        )
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        """Ensure we have an active session."""
        if self.session is None:
            ssl_context = None
            if self.config.ssl:
                import ssl
                ssl_context = ssl.create_default_context()
                if self.config.ssl.cert_path:
                    ssl_context.load_cert_chain(
                        self.config.ssl.cert_path,
                        self.config.ssl.key_path
                    )

            self.session = aiohttp.ClientSession(ssl=ssl_context)

    async def send_file(self, filepath: str, transaction_id: str) -> bool:
        """Send file via HTTP."""
        await self._ensure_session()
        
        async with aiofiles.open(filepath, 'rb') as f:
            data = await f.read()

        headers = dict(self.config.headers or {})
        # Replace template variables in headers
        replacements = {
            '{{uuid}}': transaction_id,
            '{{filename}}': os.path.basename(filepath),
            '{{username}}': self.username
        }
        headers = {
            k: v.replace('{{uuid}}', transaction_id)
                 .replace('{{filename}}', os.path.basename(filepath))
                 .replace('{{username}}', self.username)
            for k, v in headers.items()
        }

        try:
            async with self.session.request(
                self.config.method,
                self.config.url,
                data=data,
                headers=headers
            ) as response:
                return response.status < 400
        except Exception as e:
            self.logger.error(f"HTTP request failed: {str(e)}")
            return False


class SFTPJob(Job):
    """SFTP file transfer job."""

    def __init__(self, name: str, config: SFTPJobConfig):
        super().__init__(
            name=name,
            directory=config.directory,
            initial_rate=config.initial_rate,
            target_rate=config.target_rate,
            username=config.username,
            ramp_rate=config.ramp_rate
        )
        self.config = config
        self.client: Optional[asyncssh.SSHClientConnection] = None

    async def _ensure_connection(self):
        """Ensure we have an active SFTP connection."""
        if self.client is None or self.client.is_closed():
            options = {
                'username': self.config.username,
                'port': self.config.port
            }

            if self.config.key_path:
                options['client_keys'] = [self.config.key_path]
            elif self.config.password:
                options['password'] = self.config.password

            self.client = await asyncssh.connect(self.config.host, **options)

    async def send_file(self, filepath: str, transaction_id: str) -> bool:
        """Send file via SFTP."""
        try:
            await self._ensure_connection()
            
            async with self.client.start_sftp_client() as sftp:
                remote_path = os.path.join(
                    self.config.remote_path,
                    os.path.basename(filepath)
                )
                await sftp.put(filepath, remote_path)
                return True
        except Exception as e:
            self.logger.error(f"SFTP transfer failed: {str(e)}")
            if self.client:
                self.client.close()
            self.client = None
            return False


def create_job(name: str, job_type: str, config: dict) -> Job:
    """Create a job instance based on type."""
    if job_type == 'http':
        return HTTPJob(name, HTTPJobConfig(**config))
    elif job_type == 'sftp':
        return SFTPJob(name, SFTPJobConfig(**config))
    else:
        raise ValueError(f"Unknown job type: {job_type}") 