"""Main entry point for the File Transfer Harness."""

import asyncio
import logging
import os
import sys
from typing import Optional

import click
from rich.logging import RichHandler

from .config import load_config
from .jobs import create_job
from .monitor import DatabaseMonitor


def setup_logging(level: str):
    """Configure logging with rich output."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )


@click.group()
@click.option('--config', '-c', type=str, required=True, help='Path to config file')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.pass_context
def cli(ctx, config: str, verbose: bool):
    """File Transfer Harness - A tool for testing file transfer systems."""
    # Set up logging
    setup_logging(logging.DEBUG if verbose else logging.INFO)
    
    # Load configuration
    try:
        ctx.obj = load_config(config)
    except Exception as e:
        click.echo(f"Error loading config: {str(e)}", err=True)
        sys.exit(1)

    # Create output directory if it doesn't exist
    os.makedirs(ctx.obj.output_dir, exist_ok=True)


@cli.command()
@click.pass_obj
def run(config):
    """Run file transfer jobs."""
    async def main():
        # Create and start jobs
        jobs = []
        for job_config in config.jobs:
            if not job_config.enabled:
                continue
            
            try:
                job = create_job(
                    job_config.name,
                    job_config.type,
                    job_config.config.__dict__
                )
                jobs.append(job.run())
            except Exception as e:
                logging.error(f"Failed to create job {job_config.name}: {str(e)}")

        if not jobs:
            click.echo("No enabled jobs found in configuration", err=True)
            return

        # Run all jobs concurrently
        await asyncio.gather(*jobs)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        click.echo("\nStopping jobs...")
    except Exception as e:
        click.echo(f"Error running jobs: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--timespan', '-t', type=int, required=True,
              help='Time span in seconds to analyze')
@click.option('--output', '-o', type=str,
              help='Output path for the report (overrides config)')
@click.pass_obj
def report(config, timespan: int, output: Optional[str]):
    """Generate a transfer status report."""
    try:
        monitor = DatabaseMonitor(config.databases)
        report_path = output or config.report_path
        monitor.generate_report(timespan, report_path)
        click.echo(f"Report generated successfully: {report_path}")
    except Exception as e:
        click.echo(f"Error generating report: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli() 