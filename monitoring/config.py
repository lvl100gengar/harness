from pydantic_settings import BaseSettings
from typing import Optional
from pydantic import Field, validator


class DatabaseConfig(BaseSettings):
    host: str = "localhost"
    port: int = 3306
    database: str = "file_tracking"
    username: str = "reader"
    password: str = "secret"
    ssl: bool = True

    class Config:
        env_prefix = ""


class Settings(BaseSettings):
    # Web server settings
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # Mock mode settings
    mock_mode: bool = True  # Default to True for easier testing
    mock_data_rate: int = Field(default=10, description="Number of mock transactions per minute")

    # Database settings (optional when in mock mode)
    ingress_db: Optional[DatabaseConfig] = None
    egress_db: Optional[DatabaseConfig] = None

    # Application settings
    default_refresh_rate: int = Field(default=30, ge=5, le=60)
    default_display_count: int = Field(default=100, ge=10, le=1000)

    # Feature flags
    enable_sorting: bool = True
    enable_filtering: bool = True

    class Config:
        env_file = ".env"
        env_nested_delimiter = "__"

    @validator("default_refresh_rate")
    def validate_refresh_rate(cls, v):
        if not 5 <= v <= 60:
            raise ValueError("Refresh rate must be between 5 and 60 seconds")
        return v

    @validator("default_display_count")
    def validate_display_count(cls, v):
        if not 10 <= v <= 1000:
            raise ValueError("Display count must be between 10 and 1000")
        return v

    @validator("ingress_db", "egress_db")
    def validate_db_config(cls, v, values):
        if not values.get("mock_mode", False) and v is None:
            raise ValueError("Database configuration is required when not in mock mode")
        return v or DatabaseConfig() 