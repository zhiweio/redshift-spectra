"""Constants and enumerations for Redshift Spectra."""

from enum import Enum


class JobStatus(str, Enum):
    """Job lifecycle status."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


class JobType(str, Enum):
    """Type of job operation."""

    QUERY = "QUERY"
    BULK_EXPORT = "BULK_EXPORT"
    BULK_IMPORT = "BULK_IMPORT"


class BulkJobState(str, Enum):
    """Bulk job state (Salesforce Bulk v2 compatible)."""

    OPEN = "Open"
    UPLOAD_COMPLETE = "UploadComplete"
    IN_PROGRESS = "InProgress"
    JOB_COMPLETE = "JobComplete"
    FAILED = "Failed"
    ABORTED = "Aborted"


class BulkOperation(str, Enum):
    """Bulk operation type."""

    INSERT = "insert"
    UPDATE = "update"
    UPSERT = "upsert"
    DELETE = "delete"
    QUERY = "query"


class DataFormat(str, Enum):
    """Supported data formats."""

    CSV = "CSV"
    JSON = "JSON"
    PARQUET = "PARQUET"


class CompressionType(str, Enum):
    """Supported compression types (Redshift native)."""

    NONE = "NONE"
    GZIP = "GZIP"
    LZOP = "LZOP"
    BZIP2 = "BZIP2"
    ZSTD = "ZSTD"


class ContentEncoding(str, Enum):
    """Content encoding for HTTP requests."""

    GZIP = "gzip"
    IDENTITY = "identity"


# Redshift format options for COPY/UNLOAD
REDSHIFT_FORMAT_OPTIONS = {
    DataFormat.CSV: "FORMAT AS CSV",
    DataFormat.JSON: "FORMAT AS JSON 'auto'",
    DataFormat.PARQUET: "FORMAT AS PARQUET",
}

REDSHIFT_COMPRESSION_OPTIONS = {
    CompressionType.NONE: "",
    CompressionType.GZIP: "GZIP",
    CompressionType.LZOP: "LZOP",
    CompressionType.BZIP2: "BZIP2",
    CompressionType.ZSTD: "ZSTD",
}

# File extensions by format
FORMAT_EXTENSIONS = {
    DataFormat.CSV: ".csv",
    DataFormat.JSON: ".json",
    DataFormat.PARQUET: ".parquet",
}

COMPRESSION_EXTENSIONS = {
    CompressionType.NONE: "",
    CompressionType.GZIP: ".gz",
    CompressionType.LZOP: ".lzo",
    CompressionType.BZIP2: ".bz2",
    CompressionType.ZSTD: ".zst",
}

# Default configuration values
DEFAULT_RESULT_SIZE_THRESHOLD = 10000
DEFAULT_PRESIGNED_URL_EXPIRY = 3600
DEFAULT_QUERY_TIMEOUT = 300
DEFAULT_BULK_BATCH_SIZE = 10000
DEFAULT_MAX_CONCURRENT_QUERIES = 5
