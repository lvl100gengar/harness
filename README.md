# File Transfer Harness

A Python-based tool for testing file transfer systems using HTTP(S) and SFTP protocols. The harness enables testing of complex applications that process files and place them on destination servers, with reporting capabilities through MySQL databases.

## Features

- Configure and run multiple file transfer jobs concurrently
- Support for HTTP(S) and SFTP protocols with username-based authentication
- Rate-limited file transfers with configurable ramp rates
- Database status reporting with job-specific statistics
- Professional HTML reports with statistics and color-coded status indicators
- Robust error handling and logging
- Flexible time span reporting using duration strings or date ranges

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd file-transfer-harness
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

Create a YAML configuration file (see `config_example.yaml` for a complete example):

```yaml
# Global settings
log_level: INFO
output_dir: ./output
report_path: ./output/report.html

# Job definitions
jobs:
  - name: http_upload_job
    type: http
    enabled: true
    config:
      url: "https://example.com/upload"
      method: POST
      username: "http_user"  # Username for authentication and tracking
      directory: "./files_to_upload"
      rate: 60/hour  # Base transfer rate
      ramp_rate: 10/hour  # Optional: Increase rate by this amount
      ssl:
        cert_path: "/path/to/cert.pem"
        key_path: "/path/to/key.pem"
      headers:
        Content-Type: "application/octet-stream"
        X-Transaction-Id: "{{uuid}}"  # Replaced with generated UUID
        X-Filename: "{{filename}}"    # Replaced with current filename
        X-Username: "{{username}}"    # Replaced with configured username

  - name: sftp_upload_job
    type: sftp
    enabled: true
    config:
      host: "sftp.example.com"
      port: 22
      username: "sftp_user"  # Username for authentication and tracking
      key_path: "/path/to/ssh_key"  # Either key_path or password
      # password: "secret"          # Uncomment to use password auth
      directory: "./files_to_upload"
      remote_path: "/uploads"
      rate: 30/hour  # Base transfer rate
      ramp_rate: 5/hour  # Optional: Increase rate by this amount

# Database configuration
databases:
  ingress:
    host: "localhost"
    port: 3306
    database: "file_tracking"
    username: "reader"
    password: "secret"
    ssl: true
  egress:
    host: "localhost"
    port: 3306
    database: "file_tracking"
    username: "reader"
    password: "secret"
    ssl: true

# Optional monitoring configuration
monitoring:
  timespan: "1h"  # Default time window for reports
  poll_interval: 60  # Seconds between status checks
```

## Usage

The harness provides two main commands:

1. Run file transfer jobs:
```bash
python -m harness -c config.yaml run
```

2. Generate transfer status reports:
```bash
# Generate a report for the last hour using duration string
python -m harness -c config.yaml report -t 1h

# Generate a report for the last 30 minutes
python -m harness -c config.yaml report -t 30m

# Generate a report for a specific date range
python -m harness -c config.yaml report -t "2024-03-01 00:00:00/2024-03-02 00:00:00"

# Generate a report with custom output path
python -m harness -c config.yaml report -t 1h -o ./reports/hourly_report.html

# Generate a report for the last week with verbose logging
python -m harness -c config.yaml -v report -t 168h
```

The report command options:
- `-t, --timespan`: Required. Time span as duration string (e.g., '30m', '1h', '7d') or date range in format 'YYYY-MM-DD HH:MM:SS/YYYY-MM-DD HH:MM:SS'
- `-o, --output`: Optional. Custom output path for the report (overrides config)
- `-v, --verbose`: Optional. Enable verbose logging

## Report Contents

The generated HTML report includes:

1. **Overall Statistics**
   - Total number of transfers
   - Success rate
   - Number of successful transfers
   - Number of failed transfers
   - Number of timeouts
   - Min/Max/Average transfer duration

2. **Job-Specific Statistics**
   - Statistics broken down by username/job
   - Success rates per job
   - Transfer counts and durations
   - Failed/timeout counts

3. **Transfer Details**
   - UUID for each transfer
   - Username/Job identifier
   - Filename
   - Start and end times
   - Duration
   - Status (color-coded for success/failure/timeout)

4. **Unpaired Records**
   - Records found in only one database
   - Helps identify incomplete or stuck transfers
   - Grouped by username for easier debugging

## Database Schema

The harness expects the following schema in both ingress and egress databases:

```sql
CREATE TABLE file_tracking (
    uuid VARCHAR(36) PRIMARY KEY,
    username VARCHAR(255) NOT NULL,  -- Maps to job username
    filename VARCHAR(255) NOT NULL,
    startTime DATETIME NOT NULL,
    endTime DATETIME,
    status ENUM('SUCCESS', 'FAILED', 'TIMEOUT') NOT NULL
);
```

## Development

- Written in Python 3
- Uses asyncio for concurrent operations
- Follows PEP 8 style guide
- Type hints included for better IDE support

## Error Handling

The harness is designed to be resilient:
- Network errors are logged but don't stop the test
- Database errors in report generation are fatal
- File system errors are handled gracefully
- All errors are logged with appropriate detail
- Username tracking helps isolate issues to specific jobs

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

[Insert your chosen license here] 