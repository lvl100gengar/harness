"""Configuration handling for the File Transfer Harness."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Union
import yaml


@dataclass
class SSLConfig:
    cert_path: Optional[str] = None
    key_path: Optional[str] = None


@dataclass
class HTTPJobConfig:
    url: str
    method: str
    username: str
    directory: str
    initial_rate: str  # Starting transfer rate (e.g., "10/hour")
    target_rate: str   # Final transfer rate (e.g., "60/hour")
    ssl: Optional[SSLConfig] = None
    headers: Optional[Dict[str, str]] = None
    ramp_rate: Optional[str] = None  # Rate of increase (e.g., "5/hour")


@dataclass
class SFTPJobConfig:
    host: str
    port: int
    username: str
    directory: str
    remote_path: str
    initial_rate: str  # Starting transfer rate (e.g., "10/hour")
    target_rate: str   # Final transfer rate (e.g., "60/hour")
    key_path: Optional[str] = None
    password: Optional[str] = None
    ramp_rate: Optional[str] = None  # Rate of increase (e.g., "5/hour")


@dataclass
class JobConfig:
    name: str
    type: str
    enabled: bool
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

            job_config = HTTPJobConfig(
                **{k: v for k, v in config_data.items() if k != 'ssl'},
                ssl=ssl_config
            )
        elif job_data['type'] == 'sftp':
            # Handle legacy 'rate' field for backward compatibility
            config_data = job_data['config'].copy()
            if 'rate' in config_data:
                config_data['initial_rate'] = config_data['target_rate'] = config_data.pop('rate')

            job_config = SFTPJobConfig(**config_data)
        
        jobs.append(JobConfig(
            name=job_data['name'],
            type=job_data['type'],
            enabled=job_data['enabled'],
            config=job_config
        ))

    return Config(
        output_dir=raw_config.get('output_dir', './output'),
        jobs=jobs,
    )


def parse_rate(rate_str: str) -> float:
    """Parse rate string (e.g., '60/hour') into files per second."""
    number, period = rate_str.split('/')
    number = float(number)
    
    if period == 'hour':
        return number / 3600
    elif period == 'minute':
        return number / 60
    elif period == 'second':
        return number
    else:
        raise ValueError(f"Unsupported rate period: {period}") 