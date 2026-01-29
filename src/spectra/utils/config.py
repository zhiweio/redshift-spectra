"""Configuration management for Redshift Spectra.

Uses Pydantic Settings for type-safe configuration with environment variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="SPECTRA_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # AWS Configuration
    aws_region: str = Field(default="us-east-1", description="AWS region")

    # Redshift Configuration
    redshift_cluster_id: str = Field(..., description="Redshift cluster identifier")
    redshift_database: str = Field(..., description="Redshift database name")
    redshift_secret_arn: str = Field(
        ..., description="Secrets Manager ARN for Redshift credentials"
    )
    redshift_workgroup_name: str | None = Field(
        default=None, description="Redshift Serverless workgroup name (if using Serverless)"
    )

    # Redshift Session Reuse Configuration
    redshift_session_keep_alive_seconds: int = Field(
        default=3600,
        description="Session keep-alive duration in seconds (max 24 hours = 86400)",
    )
    redshift_session_idle_timeout_seconds: int = Field(
        default=300,
        description="Session idle timeout before cleanup (5 minutes default)",
    )

    # DynamoDB Configuration
    dynamodb_table_name: str = Field(
        default="spectra-jobs", description="DynamoDB table for job state"
    )
    dynamodb_sessions_table_name: str = Field(
        default="spectra-sessions", description="DynamoDB table for Redshift sessions"
    )
    dynamodb_ttl_days: int = Field(default=7, description="TTL for job records in days")

    # S3 Configuration
    s3_bucket_name: str = Field(..., description="S3 bucket for large result exports")
    s3_prefix: str = Field(default="exports/", description="S3 prefix for export files")
    presigned_url_expiry: int = Field(
        default=3600, description="Presigned URL expiration in seconds"
    )

    # Query Configuration
    result_size_threshold: int = Field(
        default=10000, description="Row count threshold before switching to S3 export"
    )
    query_timeout_seconds: int = Field(default=900, description="Query timeout in seconds")
    max_concurrent_queries: int = Field(
        default=10, description="Maximum concurrent queries per tenant"
    )

    # API Configuration
    api_version: str = Field(default="v1", description="API version prefix")
    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins")
    rate_limit_per_minute: int = Field(default=100, description="Rate limit per minute per tenant")

    # Authentication Configuration
    auth_mode: Literal["api_key", "jwt", "iam"] = Field(
        default="api_key", description="Authentication mode"
    )
    jwt_secret_arn: str | None = Field(
        default=None, description="Secrets Manager ARN for JWT secret"
    )
    jwt_issuer: str | None = Field(default=None, description="Expected JWT issuer")
    jwt_audience: str | None = Field(default=None, description="Expected JWT audience")

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Logging level"
    )
    enable_xray: bool = Field(default=True, description="Enable AWS X-Ray tracing")

    @property
    def is_serverless(self) -> bool:
        """Check if using Redshift Serverless."""
        return self.redshift_workgroup_name is not None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
