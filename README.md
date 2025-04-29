# File Transfer Harness

A Python-based tool for testing file transfer systems using HTTP(S) and SFTP protocols. The harness enables testing of complex applications that process files and place them on destination servers, with reporting capabilities through MySQL databases.

## Features

- Configure and run multiple file transfer jobs concurrently
- Support for HTTP(S) and SFTP protocols
- Rate-limited file transfers
- Database status reporting
- Professional HTML reports with statistics
- Robust error handling and logging

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
      directory: "./files_to_upload"
      rate: 60/hour
      headers:
        Content-Type: "application/octet-stream"
        X-Transaction-Id: "{{uuid}}"
        X-Filename: "{{filename}}"

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
```

## Usage

The harness provides two main commands:

1. Run file transfer jobs:
```bash
python -m harness -c config.yaml run
```

2. Generate transfer status reports:
```bash
# Generate a report for the last hour
python -m harness -c config.yaml report -t 3600

# Generate a report for the last 24 hours
python -m harness -c config.yaml report -t 86400

# Generate a report with custom output path
python -m harness -c config.yaml report -t 3600 -o ./reports/hourly_report.html

# Generate a report for the last week with verbose logging
python -m harness -c config.yaml -v report -t 604800
```

The report command options:
- `-t, --timespan`: Required. Time span in seconds to analyze (e.g., 3600 for 1 hour)
- `-o, --output`: Optional. Custom output path for the report (overrides config)
- `-v, --verbose`: Optional. Enable verbose logging

## Report Contents

The generated HTML report includes:

1. **Summary Statistics**
   - Total number of transfers
   - Success rate
   - Number of successful transfers
   - Number of failed transfers
   - Number of timeouts
   - Average transfer duration

2. **Transfer Details**
   - UUID for each transfer
   - Filename
   - Start and end times
   - Duration
   - Status (color-coded for success/failure/timeout)

3. **Unpaired Records**
   - Records found in only one database
   - Helps identify incomplete or stuck transfers

## Database Schema

The harness expects the following schema in both ingress and egress databases:

```sql
CREATE TABLE file_tracking (
    uuid VARCHAR(36) PRIMARY KEY,
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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

[Insert your chosen license here] 