"""Configuration handling for the File Transfer Harness."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Union, Literal
import yaml


@dataclass
class SSLConfig:
    """SSL configuration for HTTP jobs."""
    cert_path: Optional[str] = None
    key_path: Optional[str] = None


@dataclass
class HTTPJobConfig:
    """Configuration for HTTP transfer jobs.
    
    Required Parameters:
        directory (str): Path to directory containing files to transfer
        initial_rate (str): Initial transfer rate (e.g., "10/s", "5/min", "100/hour")
        target_rate (str): Target transfer rate to ramp up to
        url (str): Target URL for HTTP uploads
    
    Optional Parameters:
        method (str): HTTP method to use (default: 'POST')
        headers (Dict[str, str]): HTTP headers. Supports templates:
            - {{uuid}}: Replaced with generated transaction ID
            - {{filename}}: Replaced with current file name
        ssl (SSLConfig): SSL configuration for HTTPS
        ramp_rate (str): Rate at which to increase transfers (e.g., "1/s")
        transfer_mode (str): "sequential" or "concurrent" (default: "sequential")
        max_concurrent_transfers (int): Max concurrent transfers (default: CPU count * 4)
    """
    # Required parameters
    directory: str
    initial_rate: str
    target_rate: str
    url: str
    # Optional parameters
    method: str = 'POST'
    headers: Optional[Dict[str, str]] = None
    ssl: Optional[SSLConfig] = None
    ramp_rate: Optional[str] = None
    transfer_mode: str = 'sequential'
    max_concurrent_transfers: Optional[int] = None


@dataclass
class SFTPJobConfig:
    """Configuration for SFTP transfer jobs.
    
    Required Parameters:
        directory (str): Path to directory containing files to transfer
        initial_rate (str): Initial transfer rate (e.g., "10/s", "5/min", "100/hour")
        target_rate (str): Target transfer rate to ramp up to
        host (str): SFTP server hostname/IP
        username (str): SFTP username
        remote_path (str): Remote directory path for uploads
    
    Optional Parameters:
        port (int): SFTP port (default: 22)
        password (str): Password for authentication (either password or key_path required)
        key_path (str): Path to SSH private key (either password or key_path required)
        ramp_rate (str): Rate at which to increase transfers (e.g., "1/s")
        transfer_mode (str): "sequential" or "concurrent" (default: "sequential")
        max_concurrent_transfers (int): Max concurrent transfers (default: CPU count * 4)
    """
    # Required parameters
    directory: str
    initial_rate: str
    target_rate: str
    host: str
    username: str
    remote_path: str
    # Optional parameters
    port: int = 22
    password: Optional[str] = None
    key_path: Optional[str] = None
    ramp_rate: Optional[str] = None
    transfer_mode: str = 'sequential'
    max_concurrent_transfers: Optional[int] = None


@dataclass
class JobConfig:
    """Configuration for a single job.
    
    Parameters:
        name (str): Unique name for the job
        type (str): Job type ("http" or "sftp")
        config (Union[HTTPJobConfig, SFTPJobConfig]): Job-specific configuration
    """
    name: str
    type: str
    config: Union[HTTPJobConfig, SFTPJobConfig]


@dataclass
class Config:
    output_dir: str
    jobs: List[JobConfig]


def load_config(config_path: str) -> Config:
    """Load configuration from YAML file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        raw_config = yaml.safe_load(f)

    # Create job configs
    jobs = []
    for job_data in raw_config.get('jobs', []):
        job_config = None
        if job_data['type'] == 'http':
            ssl_config = None
            if 'ssl' in job_data['config']:
                ssl_config = SSLConfig(**job_data['config']['ssl'])

            # Handle legacy 'rate' field for backward compatibility
            config_data = job_data['config'].copy()
            if 'rate' in config_data:
                config_data['initial_rate'] = config_data['target_rate'] = config_data.pop('rate')

            # Set default values for new fields if not present
            if 'transfer_mode' not in config_data:
                config_data['transfer_mode'] = "sequential"

            job_config = HTTPJobConfig(
                **{k: v for k, v in config_data.items() if k != 'ssl'},
                ssl=ssl_config
            )
        elif job_data['type'] == 'sftp':
            # Handle legacy 'rate' field for backward compatibility
            config_data = job_data['config'].copy()
            if 'rate' in config_data:
                config_data['initial_rate'] = config_data['target_rate'] = config_data.pop('rate')

            # Set default values for new fields if not present
            if 'transfer_mode' not in config_data:
                config_data['transfer_mode'] = "sequential"

            job_config = SFTPJobConfig(**config_data)
        
        jobs.append(JobConfig(
            name=job_data['name'],
            type=job_data['type'],
            config=job_config
        ))

    return Config(
        output_dir=raw_config.get('output_dir', './output'),
        jobs=jobs
    )


def parse_rate(rate_str: str) -> float:
    """Parse a rate string into files per second.
    
    Examples:
        "10/s" -> 10.0
        "5/second" -> 5.0
        "100/min" -> 1.67
        "1000/hour" -> 0.28
    """
    if not rate_str:
        return 0.0

    try:
        number, unit = rate_str.split('/')
        number = float(number)
        unit = unit.lower().strip()

        if unit in ('s', 'sec', 'second', 'seconds'):
            return number
        elif unit in ('m', 'min', 'minute', 'minutes'):
            return number / 60
        elif unit in ('h', 'hour', 'hours'):
            return number / 3600
        else:
            raise ValueError(f"Unknown rate unit: {unit}")
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid rate format: {rate_str}") from e 