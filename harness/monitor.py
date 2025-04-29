"""Database monitoring and reporting module."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import mysql.connector
from jinja2 import Environment, PackageLoader

from .config import DatabaseConfig, MonitoringConfig


class TransferRecord:
    """Represents a file transfer record from the database."""
    def __init__(self, uuid: str, filename: str, start_time: datetime,
                 end_time: Optional[datetime], status: str):
        self.uuid = uuid
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

    def __init__(self, db_configs: Dict[str, DatabaseConfig]):
        self.db_configs = db_configs
        self.logger = logging.getLogger("monitor")

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
            SELECT uuid, filename, startTime, endTime, status
            FROM file_tracking
            WHERE startTime >= %s
        """
        cursor.execute(query, (start_time,))
        
        records = []
        for row in cursor:
            records.append(TransferRecord(
                uuid=row['uuid'],
                filename=row['filename'],
                start_time=row['startTime'],
                end_time=row['endTime'],
                status=row['status']
            ))
        
        cursor.close()
        return records

    def _generate_report(self, ingress_records: List[TransferRecord],
                        egress_records: List[TransferRecord],
                        unpaired_records: List[Tuple[str, Optional[TransferRecord], Optional[TransferRecord]]],
                        output_path: str):
        """Generate HTML report."""
        # Calculate statistics
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

        stats = {
            'total': total_transfers,
            'successful': successful_transfers,
            'failed': failed_transfers,
            'timeout': timeout_transfers,
            'success_rate': (successful_transfers / total_transfers * 100) if total_transfers > 0 else 0,
            'min_duration': min(durations) if durations else None,
            'max_duration': max(durations) if durations else None,
            'avg_duration': sum(durations) / len(durations) if durations else None
        }

        # Load template and render
        env = Environment(loader=PackageLoader('harness', 'templates'))
        template = env.get_template('report.html')
        
        html = template.render(
            timestamp=datetime.now(),
            stats=stats,
            transfers=[(i, e) for i in ingress_records for e in egress_records if i.uuid == e.uuid],
            unpaired=unpaired_records
        )

        with open(output_path, 'w') as f:
            f.write(html)

    def generate_report(self, timespan_seconds: int, report_path: str):
        """Generate a one-time report for the specified timespan."""
        try:
            # Calculate time window
            end_time = datetime.now()
            start_time = end_time - timedelta(seconds=timespan_seconds)

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
            self._generate_report(ingress_records, egress_records, unpaired, report_path)
            
            self.logger.info(
                f"Report generated: {len(ingress_records)} ingress records, "
                f"{len(egress_records)} egress records"
            )

        except Exception as e:
            self.logger.error(f"Error generating report: {str(e)}")
            raise 