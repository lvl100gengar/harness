"""Database monitoring and reporting module."""

import logging
from datetime import datetime, timedelta
import re
from typing import Dict, List, Optional, Tuple

import mysql.connector
from jinja2 import Environment, PackageLoader

from .config import Config, DatabaseConfig, MonitoringConfig, JobConfig


class TransferRecord:
    """Represents a file transfer record from the database."""
    def __init__(self, uuid: str, username: str, filename: str, start_time: datetime,
                 end_time: Optional[datetime], status: str):
        self.uuid = uuid
        self.username = username
        self.filename = filename
        self.start_time = start_time
        self.end_time = end_time
        self.status = status

    @property
    def duration(self) -> Optional[float]:
        """Calculate duration in seconds if both times are available."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


class DatabaseMonitor:
    """Generates reports from database transfer records."""

    def __init__(self, config: Config):
        self.db_configs = config.databases
        self.jobs = config.jobs
        self.logger = logging.getLogger("monitor")

    def _parse_timespan(self, timespan: str) -> timedelta:
        """Parse timespan string like '30m' or '1h' into timedelta."""
        match = re.match(r'^(\d+)([smh])$', timespan)
        if not match:
            raise ValueError("Invalid timespan format. Use e.g. '30m' or '1h'")
        
        value, unit = int(match.group(1)), match.group(2)
        if unit == 's':
            return timedelta(seconds=value)
        elif unit == 'm':
            return timedelta(minutes=value)
        else:  # unit == 'h'
            return timedelta(hours=value)

    def _connect_db(self, config: DatabaseConfig) -> mysql.connector.MySQLConnection:
        """Create a database connection."""
        return mysql.connector.connect(
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.username,
            password=config.password,
            ssl_disabled=not config.ssl
        )

    def _query_records(self, conn: mysql.connector.MySQLConnection,
                      start_time: datetime) -> List[TransferRecord]:
        """Query transfer records from a database."""
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT uuid, username, filename, startTime, endTime, status
            FROM file_tracking
            WHERE startTime >= %s
        """
        cursor.execute(query, (start_time,))
        
        records = []
        for row in cursor:
            records.append(TransferRecord(
                uuid=row['uuid'],
                username=row['username'],
                filename=row['filename'],
                start_time=row['startTime'],
                end_time=row['endTime'],
                status=row['status']
            ))
        
        cursor.close()
        return records

    def _calculate_job_stats(self, ingress_records: List[TransferRecord],
                           egress_records: List[TransferRecord]) -> Dict[str, Dict]:
        """Calculate statistics grouped by job (username)."""
        stats_by_job = {}
        
        # Group records by username
        for ingress in ingress_records:
            if ingress.username not in stats_by_job:
                # Find corresponding job config
                job_config = next(
                    (job for job in self.jobs if job.config.username == ingress.username),
                    None
                )
                
                stats_by_job[ingress.username] = {
                    'total': 0,
                    'successful': 0,
                    'failed': 0,
                    'timeout': 0,
                    'durations': [],
                    'job_config': job_config
                }
            
            stats_by_job[ingress.username]['total'] += 1
            
            # Find matching egress record
            egress = next((e for e in egress_records if e.uuid == ingress.uuid), None)
            if egress:
                if egress.status == 'SUCCESS':
                    stats_by_job[ingress.username]['successful'] += 1
                elif egress.status == 'FAILED':
                    stats_by_job[ingress.username]['failed'] += 1
                else:  # TIMEOUT
                    stats_by_job[ingress.username]['timeout'] += 1
                
                if egress.end_time:
                    duration = (egress.end_time - ingress.start_time).total_seconds()
                    stats_by_job[ingress.username]['durations'].append(duration)
        
        # Calculate additional statistics
        for stats in stats_by_job.values():
            durations = stats['durations']
            stats['success_rate'] = (stats['successful'] / stats['total'] * 100) if stats['total'] > 0 else 0
            stats['min_duration'] = min(durations) if durations else None
            stats['max_duration'] = max(durations) if durations else None
            stats['avg_duration'] = sum(durations) / len(durations) if durations else None
            del stats['durations']  # Remove raw durations from final stats
        
        return stats_by_job

    def _generate_report(self, ingress_records: List[TransferRecord],
                        egress_records: List[TransferRecord],
                        unpaired_records: List[Tuple[str, Optional[TransferRecord], Optional[TransferRecord]]],
                        output_path: str,
                        start_time: datetime,
                        end_time: datetime):
        """Generate HTML report."""
        # Calculate overall statistics
        total_transfers = len(ingress_records)
        successful_transfers = sum(1 for r in egress_records if r.status == 'SUCCESS')
        failed_transfers = sum(1 for r in egress_records if r.status == 'FAILED')
        timeout_transfers = sum(1 for r in egress_records if r.status == 'TIMEOUT')

        # Calculate durations for completed transfers
        durations = []
        for ingress in ingress_records:
            for egress in egress_records:
                if ingress.uuid == egress.uuid and egress.end_time:
                    duration = (egress.end_time - ingress.start_time).total_seconds()
                    durations.append(duration)

        overall_stats = {
            'total': total_transfers,
            'successful': successful_transfers,
            'failed': failed_transfers,
            'timeout': timeout_transfers,
            'success_rate': (successful_transfers / total_transfers * 100) if total_transfers > 0 else 0,
            'min_duration': min(durations) if durations else None,
            'max_duration': max(durations) if durations else None,
            'avg_duration': sum(durations) / len(durations) if durations else None
        }

        # Calculate job-specific statistics
        job_stats = self._calculate_job_stats(ingress_records, egress_records)

        # Load template and render
        env = Environment(loader=PackageLoader('harness', 'templates'))
        template = env.get_template('report.html')
        
        html = template.render(
            timestamp=datetime.now(),
            start_time=start_time,
            end_time=end_time,
            overall_stats=overall_stats,
            job_stats=job_stats,
            transfers=[(i, e) for i in ingress_records for e in egress_records if i.uuid == e.uuid],
            unpaired=unpaired_records
        )

        with open(output_path, 'w') as f:
            f.write(html)

    def generate_report(self, timespan: str, report_path: str):
        """Generate a one-time report for the specified timespan.
        
        Args:
            timespan: Either a duration string (e.g. '30m', '1h') or
                     a datetime span in ISO format 'YYYY-MM-DD HH:MM:SS/YYYY-MM-DD HH:MM:SS'
        """
        try:
            # Parse timespan
            if '/' in timespan:
                # Datetime span
                start_str, end_str = timespan.split('/')
                start_time = datetime.fromisoformat(start_str.strip())
                end_time = datetime.fromisoformat(end_str.strip())
            else:
                # Duration string
                end_time = datetime.now()
                start_time = end_time - self._parse_timespan(timespan)

            self.logger.info(f"Generating report for period: {start_time} to {end_time}")

            # Query both databases
            ingress_conn = self._connect_db(self.db_configs['ingress'])
            egress_conn = self._connect_db(self.db_configs['egress'])

            try:
                ingress_records = self._query_records(ingress_conn, start_time)
                egress_records = self._query_records(egress_conn, start_time)
            finally:
                ingress_conn.close()
                egress_conn.close()

            # Find unpaired records
            ingress_uuids = {r.uuid for r in ingress_records}
            egress_uuids = {r.uuid for r in egress_records}
            
            unpaired = []
            
            # Records in ingress but not in egress
            for uuid in ingress_uuids - egress_uuids:
                ingress_record = next(r for r in ingress_records if r.uuid == uuid)
                unpaired.append((uuid, ingress_record, None))
            
            # Records in egress but not in ingress
            for uuid in egress_uuids - ingress_uuids:
                egress_record = next(r for r in egress_records if r.uuid == uuid)
                unpaired.append((uuid, None, egress_record))

            # Generate report
            self._generate_report(
                ingress_records, egress_records, unpaired, report_path,
                start_time, end_time
            )
            
            self.logger.info(
                f"Report generated: {len(ingress_records)} ingress records, "
                f"{len(egress_records)} egress records"
            )

        except Exception as e:
            self.logger.error(f"Error generating report: {str(e)}")
            raise 