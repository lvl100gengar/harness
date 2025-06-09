# File Transfer Harness

A Python-based tool for testing file transfer systems using HTTP(S) and SFTP protocols.

## Features

- Configure and run multiple file transfer jobs concurrently
- Support for HTTP(S) and SFTP protocols with username-based authentication
- Rate-limited file transfers with configurable ramp rates
- Robust error handling

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
output_dir: ./output

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
      initial_rate: "10/hour"  # Start at 10 files per hour
      target_rate: "60/hour"   # Ramp up to 60 files per hour
      ramp_rate: "10/hour"     # Increase by 10 files per hour
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
      initial_rate: "30/hour"
      target_rate: "30/hour"
      ramp_rate: "5/hour"       # Optional: Increase rate by this amount
```

## Usage

To run the file transfer jobs:
```bash
python -m harness -c config.yaml run
```

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