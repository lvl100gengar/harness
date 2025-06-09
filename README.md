# File Transfer Harness

A Python-based tool for testing file transfer systems using HTTP(S) and SFTP protocols.

## Features

- Multiple concurrent file transfer jobs
- Support for HTTP(S) and SFTP protocols
- Rate-limited transfers with configurable ramp-up
- Sequential or concurrent transfer modes
- Detailed logging and metrics
- Template support in HTTP headers

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

Create a YAML configuration file (see `config_example.yaml` for a complete example).

### HTTP Job Configuration

Required parameters:
- `directory`: Path to directory containing files to transfer
- `initial_rate`: Initial transfer rate (e.g., "10/s", "5/min", "100/hour")
- `target_rate`: Target transfer rate to ramp up to
- `url`: Target URL for HTTP uploads

Optional parameters:
- `method`: HTTP method (default: POST)
- `headers`: Custom HTTP headers with template support:
  - `{{uuid}}`: Replaced with generated transaction ID
  - `{{filename}}`: Replaced with current file name
- `ssl`: SSL configuration for HTTPS connections
- `ramp_rate`: Rate at which to increase transfers
- `transfer_mode`: "sequential" or "concurrent" (default: sequential)
- `max_concurrent_transfers`: Maximum parallel transfers

### SFTP Job Configuration

Required parameters:
- `directory`: Path to directory containing files to transfer
- `initial_rate`: Initial transfer rate (e.g., "10/s", "5/min", "100/hour")
- `target_rate`: Target transfer rate to ramp up to
- `host`: SFTP server hostname/IP
- `username`: SFTP username
- `remote_path`: Remote directory path for uploads

Optional parameters:
- `port`: SFTP port (default: 22)
- `password`: Password for authentication
- `key_path`: Path to SSH private key (either password or key_path required)
- `ramp_rate`: Rate at which to increase transfers
- `transfer_mode`: "sequential" or "concurrent" (default: sequential)
- `max_concurrent_transfers`: Maximum parallel transfers

### Example Configuration

```yaml
# Global settings
output_dir: ./output

jobs:
  # HTTP Upload Job
  - name: http_upload_job
    type: http
    config:
      url: "https://example.com/upload"
      directory: "./files_to_upload"
      initial_rate: "10/hour"
      target_rate: "60/hour"
      ramp_rate: "10/hour"
      headers:
        X-Transaction-Id: "{{uuid}}"
        X-Filename: "{{filename}}"

  # SFTP Upload Job
  - name: sftp_upload_job
    type: sftp
    config:
      host: "sftp.example.com"
      username: "sftp_user"
      directory: "./files_to_upload"
      remote_path: "/uploads"
      initial_rate: "30/hour"
      target_rate: "30/hour"
      key_path: "/path/to/ssh_key"
```

## Usage

Run the harness with your configuration:

```bash
python -m harness -c config.yaml run
```

The harness will:
1. Start all configured jobs
2. Monitor transfer rates and adjust as configured
3. Log detailed metrics to harness.log
4. Display summary statistics in the console

## Logging

- Console output shows job status and summary metrics
- Detailed logs are written to harness.log
- Transfer metrics are logged every minute

## Development

- Written in Python 3
- Uses asyncio for concurrent operations
- Follows PEP 8 style guide
- Type hints included for better IDE support

## Error Handling

The harness is designed to be resilient:
- Network errors are logged but don't stop the test
- File system errors are handled gracefully

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

[Insert your chosen license here] 