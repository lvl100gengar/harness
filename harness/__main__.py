"""Main entry point for the File Transfer Harness."""

import asyncio
import os
from typing import List

import click

from .config import load_config, JobConfig
from .jobs import create_job


@click.group()
@click.option('--config', '-c', type=str, required=True, help='Path to config file')
@click.pass_context
def cli(ctx, config: str):
    """File Transfer Harness - A tool for testing file transfer systems."""
    try:
        ctx.obj = load_config(config)
    except Exception as e:
        click.echo(f"Error loading config: {str(e)}", err=True)
        exit(1)

    os.makedirs(ctx.obj.output_dir, exist_ok=True)


@cli.command()
@click.pass_obj
def run(config):
    """Run file transfer jobs."""
    async def main():
        # Create and start jobs
        jobs = []
        job_configs: List[JobConfig] = config.jobs
        for job_config in job_configs:
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
                click.echo(f"Failed to create job {job_config.name}: {str(e)}", err=True)

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
        exit(1)


if __name__ == '__main__':
    cli() 