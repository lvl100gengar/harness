"""Main entry point for the File Transfer Harness."""

import asyncio
import logging
import os
import sys
from typing import List

import click
import structlog

from .config import load_config, JobConfig
from .jobs import create_job

def configure_logging(debug: bool = False):
    """Configure structured logging."""
    # Configure root logger to only show warnings and errors
    logging.basicConfig(
        level=logging.WARNING,  # Root logger only shows warnings and errors
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True
    )

    # Configure our module's loggers
    harness_logger = logging.getLogger('harness')
    jobs_logger = logging.getLogger('harness.jobs')
    status_logger = logging.getLogger('harness.status')

    # Set up file handler for debug logs
    file_handler = logging.FileHandler('harness.log')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))

    # Set up console handler for status updates
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    
    # Configure harness logger
    harness_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    harness_logger.addHandler(file_handler)
    harness_logger.propagate = False  # Don't propagate to root logger
    
    # Configure jobs logger
    jobs_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    jobs_logger.addHandler(file_handler)
    jobs_logger.propagate = False  # Don't propagate to root logger
    
    # Configure status logger (always INFO for user feedback)
    status_logger.setLevel(logging.INFO)
    status_logger.addHandler(console_handler)
    status_logger.propagate = False  # Don't propagate to root logger

    # Configure third-party loggers
    if debug:
        for logger_name in ['asyncio', 'aiohttp', 'asyncssh']:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
            logger.propagate = False  # Don't propagate to root logger
    else:
        # In non-debug mode, suppress third-party logging
        for logger_name in ['asyncio', 'aiohttp', 'asyncssh']:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.WARNING)
            logger.propagate = False  # Don't propagate to root logger

@click.group()
@click.option('--config', '-c', type=str, required=True, help='Path to config file')
@click.pass_context
def cli(ctx, config: str):
    """File Transfer Harness - A tool for testing file transfer systems."""
    try:
        ctx.obj = load_config(config)
    except Exception as e:
        click.echo(f"Error loading config: {str(e)}", err=True)
        sys.exit(1)

    os.makedirs(ctx.obj.output_dir, exist_ok=True)


@cli.command()
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.pass_obj
def run(config, debug: bool):
    """Run file transfer jobs."""
    # Configure logging
    configure_logging(debug)
    logger = logging.getLogger('harness')
    
    async def main():
        # Create and start jobs
        jobs = []
        job_configs: List[JobConfig] = config.jobs
        for job_config in job_configs:
            try:
                job = create_job(
                    job_config.name,
                    job_config.type,
                    job_config.config.__dict__
                )
                jobs.append(job.run())
            except Exception as e:
                logger.error(f"Failed to create job {job_config.name}: {str(e)}")

        if not jobs:
            logger.error("No jobs found in configuration")
            return

        # Run all jobs concurrently
        await asyncio.gather(*jobs)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopping jobs...")
    except Exception as e:
        logger.error(f"Error running jobs: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    cli() 