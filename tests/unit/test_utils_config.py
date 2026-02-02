"""Unit tests for configuration module.

Tests cover:
- Settings loading from environment
- Default values
- Property methods
- Validation
"""

import os
from unittest.mock import patch

import pytest

from spectra.utils.config import Settings, get_settings


def get_clean_env(extra_vars: dict[str, str] | None = None) -> dict[str, str]:
    """Create a clean environment with only required SPECTRA_ vars.

    Removes all existing SPECTRA_ prefixed vars to ensure test isolation.
    """
    # Start with non-SPECTRA vars from current environment
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("SPECTRA_")}

    # Add required vars
    clean_env.update(
        {
            "SPECTRA_AWS_REGION": "us-east-1",
            "SPECTRA_REDSHIFT_CLUSTER_ID": "test-cluster",
            "SPECTRA_REDSHIFT_DATABASE": "test_db",
            "SPECTRA_REDSHIFT_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
            "SPECTRA_S3_BUCKET_NAME": "test-bucket",
        }
    )

    # Add extra vars if provided
    if extra_vars:
        clean_env.update(extra_vars)

    return clean_env


class TestSettings:
    """Tests for Settings class."""

    @pytest.fixture
    def env_vars(self) -> dict[str, str]:
        """Required environment variables for Settings."""
        return {
            "SPECTRA_AWS_REGION": "us-east-1",
            "SPECTRA_REDSHIFT_CLUSTER_ID": "test-cluster",
            "SPECTRA_REDSHIFT_DATABASE": "test_db",
            "SPECTRA_REDSHIFT_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
            "SPECTRA_S3_BUCKET_NAME": "test-bucket",
        }

    def test_settings_load_from_env(self, env_vars: dict[str, str]) -> None:
        """Test settings load from environment variables."""
        with patch.dict(os.environ, get_clean_env(), clear=True):
            # Clear the cache
            get_settings.cache_clear()
            # Create Settings without loading .env file
            settings = Settings(_env_file=None)

            assert settings.aws_region == "us-east-1"
            assert settings.redshift_cluster_id == "test-cluster"
            assert settings.redshift_database == "test_db"
            assert settings.s3_bucket_name == "test-bucket"

    def test_default_values(self, env_vars: dict[str, str]) -> None:
        """Test default values are applied."""
        with patch.dict(os.environ, get_clean_env(), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            # Check defaults
            assert settings.dynamodb_table_name == "spectra-jobs"
            assert settings.dynamodb_sessions_table_name == "spectra-sessions"
            assert settings.dynamodb_ttl_days == 7
            assert settings.result_size_threshold == 10000
            assert settings.query_timeout_seconds == 900
            assert settings.max_concurrent_queries == 10
            assert settings.presigned_url_expiry == 3600

    def test_session_configuration(self, env_vars: dict[str, str]) -> None:
        """Test session-related settings."""
        with patch.dict(os.environ, get_clean_env(), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.redshift_session_keep_alive_seconds == 3600
            assert settings.redshift_session_idle_timeout_seconds == 300

    def test_sql_security_settings(self, env_vars: dict[str, str]) -> None:
        """Test SQL security settings."""
        extra_vars = {
            "SPECTRA_SQL_SECURITY_LEVEL": "strict",
            "SPECTRA_SQL_MAX_QUERY_LENGTH": "50000",
            "SPECTRA_SQL_MAX_JOINS": "5",
            "SPECTRA_SQL_MAX_SUBQUERIES": "3",
            "SPECTRA_SQL_ALLOW_CTE": "false",
            "SPECTRA_SQL_ALLOW_UNION": "true",
        }
        with patch.dict(os.environ, get_clean_env(extra_vars), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.sql_security_level == "strict"
            assert settings.sql_max_query_length == 50000
            assert settings.sql_max_joins == 5
            assert settings.sql_max_subqueries == 3
            assert settings.sql_allow_cte is False
            assert settings.sql_allow_union is True

    def test_sql_security_defaults(self, env_vars: dict[str, str]) -> None:
        """Test SQL security default settings."""
        with patch.dict(os.environ, get_clean_env(), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.sql_security_level == "standard"
            assert settings.sql_max_query_length == 100000
            assert settings.sql_max_joins == 10
            assert settings.sql_max_subqueries == 5
            assert settings.sql_allow_cte is True
            assert settings.sql_allow_union is False

    def test_is_serverless_false(self, env_vars: dict[str, str]) -> None:
        """Test is_serverless property when using cluster."""
        with patch.dict(os.environ, get_clean_env(), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.is_serverless is False

    def test_is_serverless_true(self, env_vars: dict[str, str]) -> None:
        """Test is_serverless property when using serverless."""
        extra_vars = {"SPECTRA_REDSHIFT_WORKGROUP_NAME": "default-workgroup"}
        with patch.dict(os.environ, get_clean_env(extra_vars), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.is_serverless is True

    def test_auth_mode_options(self, env_vars: dict[str, str]) -> None:
        """Test different auth mode values."""
        for mode in ["api_key", "jwt", "iam"]:
            extra_vars = {"SPECTRA_AUTH_MODE": mode}
            with patch.dict(os.environ, get_clean_env(extra_vars), clear=True):
                get_settings.cache_clear()
                settings = Settings(_env_file=None)
                assert settings.auth_mode == mode

    def test_log_level_options(self, env_vars: dict[str, str]) -> None:
        """Test different log level values."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            extra_vars = {"SPECTRA_LOG_LEVEL": level}
            with patch.dict(os.environ, get_clean_env(extra_vars), clear=True):
                get_settings.cache_clear()
                settings = Settings(_env_file=None)
                assert settings.log_level == level

    def test_cors_origins_list(self, env_vars: dict[str, str]) -> None:
        """Test CORS origins as list."""
        with patch.dict(os.environ, get_clean_env(), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert isinstance(settings.cors_origins, list)
            assert "*" in settings.cors_origins

    def test_api_configuration(self, env_vars: dict[str, str]) -> None:
        """Test API-related settings."""
        with patch.dict(os.environ, get_clean_env(), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.api_version == "v1"
            assert settings.rate_limit_per_minute == 100

    def test_jwt_settings(self, env_vars: dict[str, str]) -> None:
        """Test JWT authentication settings."""
        extra_vars = {
            "SPECTRA_AUTH_MODE": "jwt",
            "SPECTRA_JWT_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123:secret:jwt",
            "SPECTRA_JWT_ISSUER": "https://auth.example.com",
            "SPECTRA_JWT_AUDIENCE": "spectra-api",
        }
        with patch.dict(os.environ, get_clean_env(extra_vars), clear=True):
            get_settings.cache_clear()
            settings = Settings(_env_file=None)

            assert settings.auth_mode == "jwt"
            assert settings.jwt_secret_arn is not None
            assert settings.jwt_issuer == "https://auth.example.com"
            assert settings.jwt_audience == "spectra-api"


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_cached(self) -> None:
        """Test that get_settings returns cached instance."""
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the same instance due to caching
        assert settings1 is settings2

    def test_cache_clear(self) -> None:
        """Test that cache can be cleared."""
        get_settings.cache_clear()
        settings1 = get_settings()

        get_settings.cache_clear()
        settings2 = get_settings()

        # Different instances after cache clear
        assert settings1 is not settings2
