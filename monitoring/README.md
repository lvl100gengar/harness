# File Transfer Monitor

A real-time web interface for monitoring file transfer transactions across ingress and egress databases.

## Features

- Real-time transaction monitoring with configurable refresh rate
- Database connection status indicators
- Configurable number of displayed transactions
- Support for both real database connections and mock data
- Modern, responsive UI using Tailwind CSS
- Pause/Resume functionality
- Error handling and graceful degradation

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create environment file:
```bash
cp .env.example .env
```

3. Configure the environment variables in `.env`:
```ini
# Web server settings
HOST=127.0.0.1
PORT=8000
DEBUG=false

# Ingress database settings
INGRESS_DB__HOST=localhost
INGRESS_DB__PORT=3306
INGRESS_DB__DATABASE=file_tracking
INGRESS_DB__USERNAME=reader
INGRESS_DB__PASSWORD=secret
INGRESS_DB__SSL=true

# Egress database settings
EGRESS_DB__HOST=localhost
EGRESS_DB__PORT=3306
EGRESS_DB__DATABASE=file_tracking
EGRESS_DB__USERNAME=reader
EGRESS_DB__PASSWORD=secret
EGRESS_DB__SSL=true

# Application settings
DEFAULT_REFRESH_RATE=30
DEFAULT_DISPLAY_COUNT=100
MOCK_MODE=true
MOCK_DATA_RATE=10

# Feature flags
ENABLE_SORTING=true
ENABLE_FILTERING=true
```

## Usage

1. Start the server:
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

2. Open your browser and navigate to `http://127.0.0.1:8000`

## Development

The application is built with:
- FastAPI for the backend
- Tailwind CSS for styling
- Vanilla JavaScript for frontend functionality

Key components:
- `app.py`: FastAPI application and routes
- `models.py`: Data models and mock data generator
- `database.py`: Database connection and query logic
- `config.py`: Configuration management
- `static/app.js`: Frontend JavaScript
- `static/styles.css`: Custom CSS styles
- `templates/index.html`: Main HTML template

## Mock Mode

When `MOCK_MODE=true`, the application generates realistic mock data instead of connecting to databases. This is useful for:
- Development and testing
- Demonstrations
- UI/UX testing without database setup

Mock data includes:
- Various usernames and filenames
- Realistic timestamps
- Different transaction statuses (SUCCESS, FAILED, TIMEOUT)
- Simulated processing durations

## Error Handling

The application implements several error handling strategies:
- Automatic database reconnection attempts
- Visual indicators for connection status
- Detailed error messages in logs
- Graceful UI degradation during failures

## Performance Considerations

- Connection pooling for database connections
- Configurable refresh rates (5-60 seconds)
- Configurable display limits (10-1000 transactions)
- Efficient DOM updates
- Debounced API calls 