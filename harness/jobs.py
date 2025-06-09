"""Job execution module for file transfers."""

import asyncio
import logging
import os
import uuid
import time
import random
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Optional, Set, Dict
from dataclasses import dataclass
from collections import deque

import aiohttp
import asyncssh
import aiofiles

from .config import HTTPJobConfig, SFTPJobConfig, parse_rate

# Configure logging
logger = logging.getLogger('harness.jobs')
logger.setLevel(logging.DEBUG)

# File handler with debug level
file_handler = logging.FileHandler('harness.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
))
logger.addHandler(file_handler)

# Console handler with minimal output
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)  # Only show warnings and errors
console_handler.setFormatter(logging.Formatter(
    '[%(levelname)s] %(message)s'
))
logger.addHandler(console_handler)

# Create a separate logger for status updates to console
status_logger = logging.getLogger('harness.status')
status_handler = logging.StreamHandler()
status_handler.setFormatter(logging.Formatter('%(message)s'))
status_logger.addHandler(status_handler)
status_logger.setLevel(logging.INFO)

@dataclass
class TransferMetrics:
    """Metrics for a single transfer."""
    start_time: float
    end_time: Optional[float] = None
    success: Optional[bool] = None
    bytes_transferred: int = 0
    retries: int = 0

class Job(ABC):
    """Base class for transfer jobs."""

    def __init__(self, name: str, directory: str, initial_rate: str, target_rate: str,
                 username: str, ramp_rate: Optional[str] = None, transfer_mode: str = "sequential",
                 max_concurrent_transfers: Optional[int] = None):
        self.name = name
        self.directory = directory
        self.username = username
        self.transfer_mode = transfer_mode
        self.max_concurrent_transfers = max_concurrent_transfers or (os.cpu_count() * 4)

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

        # Track active transfers with a fixed-size deque for completed transfers
        self.active_transfers: Set[str] = set()
        self.transfer_metrics: Dict[str, TransferMetrics] = {}
        self.completed_transfers = deque(maxlen=10000)  # Keep last 10k transfers
        self.transfer_semaphore = asyncio.Semaphore(self.max_concurrent_transfers)
        
        # Performance metrics
        self.total_transfers = 0
        self.successful_transfers = 0
        self.failed_transfers = 0
        self.total_bytes = 0
        self.last_metrics_time = time.time()
        
        # File scanning optimization
        self.last_scan_time = 0
        self.scan_interval = 1.0  # Scan directory every second
        self.pending_files = deque()

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
            logger.info(f"Transfer rate updated: {new_rate:.2f} files/second (interval: {self.interval:.2f}s)")

        self.last_ramp_time = datetime.now()

    def _log_metrics(self) -> None:
        """Log performance metrics periodically."""
        current_time = time.time()
        elapsed = current_time - self.last_metrics_time
        
        if elapsed >= 60:  # Log metrics every minute
            success_rate = self.successful_transfers / max(self.total_transfers, 1)
            throughput = self.total_bytes / elapsed / 1024 / 1024  # MB/s
            
            # Detailed metrics to log file
            logger.info(
                f"Transfer metrics for {self.name}: "
                f"active={len(self.active_transfers)}, "
                f"total={self.total_transfers}, "
                f"success_rate={success_rate:.2%}, "
                f"throughput={throughput:.2f} MB/s"
            )
            
            # Only log to console if there's meaningful activity
            if self.total_transfers > 0:
                status_logger.info(
                    f"{self.name}: {throughput:.1f} MB/s ({success_rate:.1%} success)"
                )
            
            # Reset counters
            self.total_bytes = 0
            self.last_metrics_time = current_time

    async def _scan_directory(self) -> List[str]:
        """Scan directory for new files efficiently."""
        current_time = time.time()
        if current_time - self.last_scan_time < self.scan_interval:
            return []

        self.last_scan_time = current_time
        try:
            logger.debug(f"Scanning directory {self.directory} (exists={os.path.exists(self.directory)}, is_dir={os.path.isdir(self.directory)})")
            
            if not os.path.exists(self.directory):
                logger.error(f"Directory not found: {self.directory}")
                return []
            
            if not os.path.isdir(self.directory):
                logger.error(f"Not a directory: {self.directory}")
                return []
            
            files = []
            for f in os.listdir(self.directory):
                filepath = os.path.join(self.directory, f)
                if os.path.isfile(filepath):
                    files.append(filepath)
                    logger.debug(f"Found file: {f} ({os.path.getsize(filepath)} bytes)")
            
            if files:
                logger.debug(f"Found {len(files)} files in {self.directory}")
            else:
                logger.debug(f"No files found in {self.directory}")
            
            return files
        except Exception as e:
            logger.error(f"Failed to scan directory {self.directory}: {str(e)}")
            return []

    @abstractmethod
    async def send_file(self, filepath: str, transaction_id: str) -> bool:
        """Send a single file."""
        pass

    async def _transfer_file(self, filepath: str, transaction_id: str) -> None:
        """Handle a single file transfer with tracking."""
        async with self.transfer_semaphore:
            self.active_transfers.add(transaction_id)
            start_time = datetime.now()
            success = False

            try:
                logger.debug(
                    f"Starting transfer: {os.path.basename(filepath)} "
                    f"(job={self.name}, transaction={transaction_id})"
                )
                
                success = await self.send_file(filepath, transaction_id)
                
                if success:
                    logger.debug(
                        f"Transfer completed: {os.path.basename(filepath)} "
                        f"(job={self.name}, transaction={transaction_id})"
                    )
                else:
                    logger.error(
                        f"Transfer failed: {os.path.basename(filepath)} "
                        f"(job={self.name}, transaction={transaction_id})"
                    )
            except Exception as e:
                logger.error(
                    f"Transfer error: {os.path.basename(filepath)} - {str(e)} "
                    f"(job={self.name}, transaction={transaction_id})"
                )
                success = False

            duration = (datetime.now() - start_time).total_seconds()
            
            # Update metrics
            if success:
                self.successful_transfers += 1
            else:
                self.failed_transfers += 1
            self.total_transfers += 1
            
            try:
                file_size = os.path.getsize(filepath)
                self.transfer_metrics[transaction_id] = TransferMetrics(
                    start_time=time.time(),
                    end_time=time.time(),
                    success=success,
                    bytes_transferred=file_size if success else 0
                )
                self.active_transfers.remove(transaction_id)

                # Log transfer metrics to debug only
                logger.debug(
                    f"Transfer metrics: {os.path.basename(filepath)} - "
                    f"duration={duration:.2f}s, success={success}, size={file_size} bytes "
                    f"(job={self.name}, transaction={transaction_id})"
                )
            except Exception as e:
                logger.error(
                    f"Failed to update metrics: {os.path.basename(filepath)} - {str(e)} "
                    f"(job={self.name}, transaction={transaction_id})"
                )

    async def run(self):
        """Run the job continuously."""
        status_logger.info(
            f"Starting {self.name} ({self.transfer_mode}) - "
            f"Rate: {self.current_files_per_second:.1f} → {self.target_files_per_second:.1f} files/s"
        )

        async with self:  # Use the job as an async context manager
            tasks = set()
            while True:
                try:
                    # Update rate if ramping is enabled
                    self._update_rate()

                    # Clean up completed tasks
                    done = {t for t in tasks if t.done()}
                    tasks.difference_update(done)
                    for t in done:
                        try:
                            await t
                        except Exception as e:
                            logger.error(f"Task error: {str(e)}")

                    files = await self._scan_directory()
                    if not files:
                        await asyncio.sleep(1)
                        continue

                    for filepath in files:
                        if not os.path.isfile(filepath):
                            continue

                        transaction_id = str(uuid.uuid4())
                        
                        if self.transfer_mode == "sequential":
                            # In sequential mode, wait for each transfer to complete
                            await self._transfer_file(filepath, transaction_id)
                            # Wait for the next interval before starting the next transfer
                            await asyncio.sleep(self.interval)
                        else:
                            # In concurrent mode, start transfers at the specified rate
                            # without waiting for completion
                            if len(tasks) >= self.max_concurrent_transfers:
                                # Wait for at least one task to complete
                                done, pending = await asyncio.wait(
                                    tasks,
                                    return_when=asyncio.FIRST_COMPLETED
                                )
                                tasks.difference_update(done)
                                for t in done:
                                    try:
                                        await t
                                    except Exception as e:
                                        logger.error(f"Task error: {str(e)}")

                            task = asyncio.create_task(self._transfer_file(filepath, transaction_id))
                            tasks.add(task)
                            await asyncio.sleep(self.interval)

                except Exception as e:
                    logger.error("job_error", error=str(e))
                    await asyncio.sleep(5)  # Wait before retrying

    async def __aenter__(self):
        """Base async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Base async context manager exit."""
        pass


class HTTPJob(Job):
    """HTTP file transfer job."""

    def __init__(self, name: str, config: HTTPJobConfig):
        super().__init__(
            name=name,
            directory=config.directory,
            initial_rate=config.initial_rate,
            target_rate=config.target_rate,
            username="",  # Not used for HTTP
            ramp_rate=config.ramp_rate,
            transfer_mode=config.transfer_mode,
            max_concurrent_transfers=config.max_concurrent_transfers
        )
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.chunk_size = 64 * 1024  # 64KB chunks for streaming
        self.max_retries = 3
        self.retry_delay = 1.0  # Initial retry delay in seconds

    async def __aenter__(self):
        """Set up the HTTP session."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def _ensure_session(self):
        """Ensure we have an active session with proper configuration."""
        if self.session is None:
            logger.debug(f"Creating HTTP session for {self.config.url} ({self.config.method})")
            
            timeout = aiohttp.ClientTimeout(
                total=300,  # 5 minute total timeout
                connect=30,  # 30 second connection timeout
                sock_read=60  # 1 minute read timeout
            )
            
            # Configure connection pooling
            connector = aiohttp.TCPConnector(
                limit=self.max_concurrent_transfers,  # Match our concurrency limit
                enable_cleanup_closed=True,
                force_close=False,  # Keep connections alive
                keepalive_timeout=60,  # Keep connections alive for 60 seconds
                ttl_dns_cache=300,  # Cache DNS results for 5 minutes
            )

            if self.config.ssl:
                import ssl
                ssl_context = ssl.create_default_context()
                if self.config.ssl.cert_path:
                    ssl_context.load_cert_chain(
                        self.config.ssl.cert_path,
                        self.config.ssl.key_path
                    )
                connector = aiohttp.TCPConnector(
                    limit=self.max_concurrent_transfers,
                    enable_cleanup_closed=True,
                    force_close=False,
                    keepalive_timeout=60,
                    ttl_dns_cache=300,
                    ssl=ssl_context
                )

            try:
                self.session = aiohttp.ClientSession(
                    timeout=timeout,
                    connector=connector
                )
                logger.debug("HTTP session created")
            except Exception as e:
                logger.error(f"Failed to create HTTP session: {str(e)}")
                raise

    async def _send_with_retry(self, filepath: str, transaction_id: str, retry_count: int = 0) -> bool:
        """Send file with retry logic."""
        try:
            headers = dict(self.config.headers or {})
            replacements = {
                '{{uuid}}': transaction_id,
                '{{filename}}': os.path.basename(filepath)
                # Removed username template since it's not needed for HTTP
            }
            headers.update({
                k: v.format(**replacements)
                for k, v in headers.items()
            })
            
            file_size = os.path.getsize(filepath)
            headers['Content-Length'] = str(file_size)

            logger.debug(
                f"Starting HTTP request: {self.config.method} {self.config.url} "
                f"(file={os.path.basename(filepath)}, size={file_size} bytes)"
            )

            async with aiofiles.open(filepath, 'rb') as f:
                async with self.session.request(
                    self.config.method,
                    self.config.url,
                    data=self._stream_file(f),
                    headers=headers
                ) as response:
                    if response.status >= 400:
                        response_text = await response.text()
                        logger.error(
                            f"HTTP transfer failed: {response.status} - {response_text} "
                            f"(file={os.path.basename(filepath)}, transaction={transaction_id})"
                        )
                        return await self._handle_retry(filepath, transaction_id, retry_count)
                    
                    logger.debug(f"HTTP request complete: {response.status} (transaction={transaction_id})")
                    return True

        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error: {str(e)} (file={os.path.basename(filepath)}, transaction={transaction_id})")
            return await self._handle_retry(filepath, transaction_id, retry_count)
        except asyncio.TimeoutError:
            logger.error(f"HTTP timeout (file={os.path.basename(filepath)}, transaction={transaction_id})")
            return await self._handle_retry(filepath, transaction_id, retry_count)
        except Exception as e:
            logger.error(f"HTTP unexpected error: {str(e)} (file={os.path.basename(filepath)}, transaction={transaction_id})")
            return await self._handle_retry(filepath, transaction_id, retry_count)

    async def _handle_retry(self, filepath: str, transaction_id: str, retry_count: int) -> bool:
        """Handle retry logic for failed transfers."""
        if retry_count >= self.max_retries:
            return False
            
        # Exponential backoff
        delay = self.retry_delay * (2 ** retry_count)
        await asyncio.sleep(delay)
        
        # Ensure session is still valid
        await self._ensure_session()
        
        return await self._send_with_retry(filepath, transaction_id, retry_count + 1)

    async def _stream_file(self, file):
        """Generator to stream file in chunks."""
        while True:
            chunk = await file.read(self.chunk_size)
            if not chunk:
                break
            yield chunk

    async def send_file(self, filepath: str, transaction_id: str) -> bool:
        """Send file via HTTP with retries."""
        await self._ensure_session()
        return await self._send_with_retry(filepath, transaction_id)


class SFTPJob(Job):
    """SFTP file transfer job."""

    def __init__(self, name: str, config: SFTPJobConfig):
        super().__init__(
            name=name,
            directory=config.directory,
            initial_rate=config.initial_rate,
            target_rate=config.target_rate,
            username=config.username,
            ramp_rate=config.ramp_rate,
            transfer_mode=config.transfer_mode,
            max_concurrent_transfers=config.max_concurrent_transfers
        )
        self.config = config
        # Limit connection pool to prevent overwhelming server
        self.connection_pool: Dict[int, asyncssh.SSHClientConnection] = {}
        self.pool_semaphore = asyncio.Semaphore(min(3, self.max_concurrent_transfers))  # Even more conservative limit
        self.max_retries = 3
        self.retry_delay = 2.0  # Increased base delay
        self.chunk_size = 64 * 1024  # 64KB chunks for streaming
        self.connection_delay = 0.5  # Delay between connection attempts

    async def __aenter__(self):
        """Initialize connection pool."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up connection pool and cancel pending tasks."""
        # Cancel all pending transfer tasks
        current_task = asyncio.current_task()
        for task in asyncio.all_tasks():
            if task is not current_task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"Error during task cleanup: {str(e)}")

        # Clean up connections
        for conn in self.connection_pool.values():
            conn.close()
        self.connection_pool.clear()

    async def _get_connection(self) -> asyncssh.SSHClientConnection:
        """Get a connection from the pool or create a new one."""
        task_id = id(asyncio.current_task())
        
        if task_id in self.connection_pool:
            conn = self.connection_pool[task_id]
            if not conn.is_closed():
                return conn
            logger.debug(f"SFTP connection closed (task={task_id})")
            del self.connection_pool[task_id]

        async with self.pool_semaphore:
            # Add delay between connection attempts
            await asyncio.sleep(self.connection_delay)
            
            options = {
                'username': self.config.username,
                'port': self.config.port,
                'keepalive_interval': 10,  # More frequent keepalive
                'keepalive_count_max': 3,  # Fail faster on unresponsive connections,
                'known_hosts': None,  # Don't verify host keys for testing
                'server_host_key_algs': ['ssh-rsa', 'ecdsa-sha2-nistp256', 'ssh-ed25519']  # Accept ssh-rsa
            }

            if self.config.key_path:
                options['client_keys'] = [self.config.key_path]
            elif self.config.password:
                options['password'] = self.config.password

            logger.debug(
                f"Creating SFTP connection: {self.config.host}:{self.config.port} "
                f"(user={self.config.username}, key_algs={options['server_host_key_algs']})"
            )

            retry_count = 0
            last_error = None
            while retry_count < self.max_retries:
                try:
                    conn = await asyncssh.connect(
                        self.config.host,
                        **options
                    )
                    
                    # Test connection with a simple SFTP operation
                    async with conn.start_sftp_client() as sftp:
                        await sftp.getcwd()
                    
                    self.connection_pool[task_id] = conn
                    logger.debug(f"SFTP connection created and tested (task={task_id})")
                    return conn
                except Exception as e:
                    # Handle any authentication errors (they may have different names in different versions)
                    if any(err_type in str(type(e)) for err_type in ['AuthenticationError', 'PermissionDenied']):
                        logger.error(f"SFTP authentication failed: {str(e)}")
                        raise  # Don't retry auth failures
                    
                    last_error = e
                    retry_count += 1
                    if retry_count >= self.max_retries:
                        logger.error(f"SFTP connection failed after {retry_count} retries: {str(e)}")
                        raise
                    
                    # Exponential backoff with jitter
                    delay = (self.retry_delay * (2 ** retry_count)) + (random.random() * 0.5)
                    logger.warning(f"SFTP connection attempt {retry_count} failed, retrying in {delay:.1f}s: {str(e)}")
                    await asyncio.sleep(delay)

            if last_error:
                raise last_error

    async def _send_with_retry(self, filepath: str, transaction_id: str, retry_count: int = 0) -> bool:
        """Send file with retry logic."""
        try:
            conn = await self._get_connection()
            logger.debug(
                f"SFTP connection established: {self.config.host}:{self.config.port} "
                f"(user={self.config.username})"
            )

            async with conn.start_sftp_client() as sftp:
                remote_path = os.path.join(
                    self.config.remote_path,
                    os.path.basename(filepath)
                )
                
                logger.debug(
                    f"Starting SFTP transfer: {os.path.basename(filepath)} -> {remote_path} "
                    f"(transaction={transaction_id})"
                )
                
                # Use progress callback to track bytes transferred
                progress = {'bytes': 0}
                def callback(bytes_transferred, *_):  # Accept any arguments but only use the first
                    try:
                        if isinstance(bytes_transferred, (int, float)):
                            progress['bytes'] = int(bytes_transferred)
                        elif isinstance(bytes_transferred, bytes):
                            progress['bytes'] = len(bytes_transferred)
                        else:
                            # If we get an unexpected type, just log it and continue
                            logger.debug(
                                f"Unexpected progress callback value type: {type(bytes_transferred)} "
                                f"(value: {bytes_transferred})"
                            )
                    except Exception as e:
                        logger.debug(f"Progress callback error: {str(e)}")
                
                await sftp.put(
                    filepath,
                    remote_path,
                    block_size=self.chunk_size,
                    progress_handler=callback
                )
                
                # Get final file size for metrics
                try:
                    file_size = os.path.getsize(filepath)
                    self.total_bytes += file_size
                except Exception as e:
                    logger.error(f"Failed to get file size: {str(e)}")
                    self.total_bytes += progress['bytes']  # Use progress as fallback

                logger.debug(
                    f"SFTP transfer complete: {progress['bytes']} bytes "
                    f"(transaction={transaction_id})"
                )
                return True

        except (asyncssh.Error, OSError) as e:
            logger.error(
                f"SFTP transfer failed: {str(e)} "
                f"(file={os.path.basename(filepath)}, transaction={transaction_id})"
            )
            
            # Clean up failed connection
            task_id = id(asyncio.current_task())
            if task_id in self.connection_pool:
                self.connection_pool[task_id].close()
                del self.connection_pool[task_id]
            
            return await self._handle_retry(filepath, transaction_id, retry_count)
        except Exception as e:
            logger.error(
                f"SFTP unexpected error: {str(e)} "
                f"(file={os.path.basename(filepath)}, transaction={transaction_id})"
            )
            return await self._handle_retry(filepath, transaction_id, retry_count)

    async def _handle_retry(self, filepath: str, transaction_id: str, retry_count: int) -> bool:
        """Handle retry logic for failed transfers."""
        if retry_count >= self.max_retries:
            return False
            
        # Exponential backoff
        delay = self.retry_delay * (2 ** retry_count)
        await asyncio.sleep(delay)
        
        return await self._send_with_retry(filepath, transaction_id, retry_count + 1)

    async def send_file(self, filepath: str, transaction_id: str) -> bool:
        """Send file via SFTP with retries."""
        return await self._send_with_retry(filepath, transaction_id)


def create_job(name: str, job_type: str, config: dict) -> Job:
    """Create a job instance based on type."""
    if job_type == 'http':
        return HTTPJob(name, HTTPJobConfig(**config))
    elif job_type == 'sftp':
        return SFTPJob(name, SFTPJobConfig(**config))
    else:
        raise ValueError(f"Unknown job type: {job_type}") 