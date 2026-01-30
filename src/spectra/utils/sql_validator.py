"""SQL security validation and sanitization.

This module provides comprehensive SQL security checks to prevent:
- SQL injection attacks
- Unauthorized DDL/DML operations
- Resource abuse through expensive queries
- Access to system tables and functions
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from aws_lambda_powertools import Logger

logger = Logger()


class SQLSecurityLevel(str, Enum):
    """Security level for SQL validation."""

    STRICT = "strict"  # Only SELECT, no subqueries, no functions
    STANDARD = "standard"  # SELECT with common functions, subqueries allowed
    PERMISSIVE = "permissive"  # SELECT with most functions, CTEs allowed


class SQLValidationError(Exception):
    """Raised when SQL validation fails."""

    def __init__(self, message: str, error_code: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


@dataclass
class SQLValidationResult:
    """Result of SQL validation."""

    is_valid: bool
    sql: str
    warnings: list[str] = field(default_factory=list)
    normalized_sql: str | None = None
    query_type: str | None = None


class SQLValidator:
    """Validates SQL queries for security and compliance.

    This validator implements multiple layers of protection:
    1. Statement type validation (only SELECT allowed)
    2. Dangerous keyword detection
    3. System object access prevention
    4. SQL injection pattern detection
    5. Query complexity limits
    """

    # Forbidden statement types (DDL/DML)
    FORBIDDEN_STATEMENTS = frozenset(
        {
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "CREATE",
            "ALTER",
            "TRUNCATE",
            "GRANT",
            "REVOKE",
            "VACUUM",
            "ANALYZE",
            "COPY",
            "UNLOAD",  # UNLOAD is handled separately via export service
            "CALL",
            "EXECUTE",
            "PREPARE",
        }
    )

    # Dangerous patterns that might indicate SQL injection
    INJECTION_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        # Comment injection
        (r"--\s*$", "SQL comment at end of statement"),
        (r"/\*.*?\*/", "Block comment detected"),
        # String escape attacks
        (r"'(\s*;\s*|\s+OR\s+|\s+AND\s+)", "Potential string escape attack"),
        # Union-based injection
        (r"\bUNION\s+(ALL\s+)?SELECT\b", "UNION SELECT pattern detected"),
        # Stacked queries
        (r";\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE)", "Stacked query detected"),
        # Hex encoding attacks
        (r"0x[0-9a-fA-F]+", "Hexadecimal literal detected"),
        # CHAR() function abuse
        (r"\bCHAR\s*\(\s*\d+\s*(,\s*\d+\s*)*\)", "CHAR() function abuse"),
        # Benchmark/sleep attacks
        (r"\b(BENCHMARK|SLEEP|WAITFOR|PG_SLEEP)\s*\(", "Time-based attack pattern"),
        # System command execution
        (r"\b(EXEC|EXECUTE|XP_|SP_)\s*\(", "System execution pattern"),
    ]

    # Forbidden system objects
    FORBIDDEN_OBJECTS = frozenset(
        {
            # Redshift system tables
            "pg_catalog",
            "information_schema",
            "pg_internal",
            "stl_",
            "stv_",
            "svl_",
            "svv_",
            "sys_",
            # PostgreSQL internals
            "pg_",
        }
    )

    # Forbidden functions
    FORBIDDEN_FUNCTIONS = frozenset(
        {
            # System functions
            "pg_read_file",
            "pg_read_binary_file",
            "pg_ls_dir",
            "pg_stat_file",
            "pg_terminate_backend",
            "pg_cancel_backend",
            "pg_reload_conf",
            # Network functions
            "inet_client_addr",
            "inet_server_addr",
            # User/role functions that could leak info
            "current_setting",
            "set_config",
            # File operations
            "lo_import",
            "lo_export",
        }
    )

    # Allowed aggregate functions
    ALLOWED_AGGREGATES = frozenset(
        {
            "COUNT",
            "SUM",
            "AVG",
            "MIN",
            "MAX",
            "STDDEV",
            "VARIANCE",
            "PERCENTILE_CONT",
            "PERCENTILE_DISC",
            "MEDIAN",
            "LISTAGG",
            "ARRAY_AGG",
        }
    )

    # Allowed scalar functions
    ALLOWED_FUNCTIONS = frozenset(
        {
            # String functions
            "UPPER",
            "LOWER",
            "TRIM",
            "LTRIM",
            "RTRIM",
            "LENGTH",
            "SUBSTRING",
            "SUBSTR",
            "REPLACE",
            "CONCAT",
            "LEFT",
            "RIGHT",
            "SPLIT_PART",
            "REGEXP_SUBSTR",
            "REGEXP_REPLACE",
            "REGEXP_COUNT",
            "INITCAP",
            "REVERSE",
            # Date/time functions
            "DATE_TRUNC",
            "DATE_PART",
            "EXTRACT",
            "CURRENT_DATE",
            "CURRENT_TIMESTAMP",
            "NOW",
            "GETDATE",
            "DATEADD",
            "DATEDIFF",
            "TO_DATE",
            "TO_TIMESTAMP",
            "TO_CHAR",
            # Numeric functions
            "ABS",
            "CEIL",
            "CEILING",
            "FLOOR",
            "ROUND",
            "TRUNC",
            "MOD",
            "POWER",
            "SQRT",
            "LOG",
            "LN",
            "EXP",
            "SIGN",
            "RANDOM",
            # Null handling
            "COALESCE",
            "NVL",
            "NVL2",
            "NULLIF",
            "ISNULL",
            # Conditional
            "CASE",
            "DECODE",
            "IFF",
            # Casting
            "CAST",
            "CONVERT",
            "TRY_CAST",
            # JSON functions
            "JSON_EXTRACT_PATH_TEXT",
            "JSON_EXTRACT_ARRAY_ELEMENT_TEXT",
            "JSON_SERIALIZE",
            "JSON_PARSE",
            # Window functions
            "ROW_NUMBER",
            "RANK",
            "DENSE_RANK",
            "NTILE",
            "LAG",
            "LEAD",
            "FIRST_VALUE",
            "LAST_VALUE",
        }
    )

    def __init__(
        self,
        security_level: SQLSecurityLevel = SQLSecurityLevel.STANDARD,
        max_query_length: int = 100000,
        max_joins: int = 10,
        max_subqueries: int = 5,
        allow_cte: bool = True,
        allow_union: bool = False,
        custom_forbidden_patterns: list[tuple[str, str]] | None = None,
    ):
        """Initialize the SQL validator.

        Args:
            security_level: Level of security strictness
            max_query_length: Maximum allowed query length in characters
            max_joins: Maximum number of JOINs allowed
            max_subqueries: Maximum number of subqueries allowed
            allow_cte: Whether to allow Common Table Expressions (WITH)
            allow_union: Whether to allow UNION (except UNION SELECT injection)
            custom_forbidden_patterns: Additional regex patterns to block
        """
        self.security_level = security_level
        self.max_query_length = max_query_length
        self.max_joins = max_joins
        self.max_subqueries = max_subqueries
        self.allow_cte = allow_cte
        self.allow_union = allow_union

        # Compile regex patterns for performance
        self._injection_patterns = [
            (re.compile(pattern, re.IGNORECASE | re.DOTALL), desc)
            for pattern, desc in self.INJECTION_PATTERNS
        ]

        if custom_forbidden_patterns:
            self._injection_patterns.extend(
                [
                    (re.compile(pattern, re.IGNORECASE | re.DOTALL), desc)
                    for pattern, desc in custom_forbidden_patterns
                ]
            )

    def validate(self, sql: str) -> SQLValidationResult:
        """Validate SQL query for security compliance.

        Args:
            sql: SQL query string to validate

        Returns:
            SQLValidationResult with validation outcome

        Raises:
            SQLValidationError: If validation fails
        """
        warnings: list[str] = []

        # Step 1: Basic normalization
        normalized_sql = self._normalize_sql(sql)

        # Step 2: Length check
        if len(normalized_sql) > self.max_query_length:
            raise SQLValidationError(
                f"Query exceeds maximum length of {self.max_query_length} characters",
                error_code="QUERY_TOO_LONG",
                details={"length": len(normalized_sql), "max_length": self.max_query_length},
            )

        # Step 3: Statement type validation
        query_type = self._detect_statement_type(normalized_sql)
        if query_type != "SELECT":
            raise SQLValidationError(
                f"Only SELECT statements are allowed. Detected: {query_type}",
                error_code="FORBIDDEN_STATEMENT",
                details={"detected_type": query_type},
            )

        # Step 4: Injection pattern detection
        self._check_injection_patterns(normalized_sql)

        # Step 5: Forbidden object access
        self._check_forbidden_objects(normalized_sql)

        # Step 6: Function validation
        if self.security_level == SQLSecurityLevel.STRICT:
            self._check_strict_functions(normalized_sql)

        # Step 7: Query complexity checks
        self._check_query_complexity(normalized_sql)

        # Step 8: CTE/UNION checks
        if not self.allow_cte and re.search(r"\bWITH\b", normalized_sql, re.IGNORECASE):
            raise SQLValidationError(
                "Common Table Expressions (WITH) are not allowed",
                error_code="CTE_NOT_ALLOWED",
            )

        # UNION check (allow_union controls UNION ALL, but UNION SELECT is always blocked)
        if (
            not self.allow_union
            and re.search(r"\bUNION\b", normalized_sql, re.IGNORECASE)
            and not re.search(r"\bUNION\s+(ALL\s+)?SELECT\b", normalized_sql, re.IGNORECASE)
        ):
            warnings.append("UNION detected - ensure this is intentional")

        logger.info(
            "SQL validation passed",
            extra={
                "query_type": query_type,
                "query_length": len(normalized_sql),
                "warnings": warnings,
            },
        )

        return SQLValidationResult(
            is_valid=True,
            sql=sql,
            normalized_sql=normalized_sql,
            query_type=query_type,
            warnings=warnings,
        )

    def _normalize_sql(self, sql: str) -> str:
        """Normalize SQL for consistent validation.

        Args:
            sql: Raw SQL string

        Returns:
            Normalized SQL string
        """
        # Strip whitespace
        normalized = sql.strip()

        # Remove trailing semicolons (we only allow single statements)
        normalized = normalized.rstrip(";")

        # Collapse multiple whitespace
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized

    def _detect_statement_type(self, sql: str) -> str:
        """Detect the type of SQL statement.

        Args:
            sql: Normalized SQL string

        Returns:
            Statement type (SELECT, INSERT, etc.)
        """
        upper_sql = sql.upper().strip()

        # Handle CTE (WITH ... SELECT)
        if upper_sql.startswith("WITH"):
            # Find the main statement after WITH clause
            # This is a simplified check
            if "SELECT" in upper_sql:
                return "SELECT"
            return "WITH"

        # Check for forbidden statements
        for stmt in self.FORBIDDEN_STATEMENTS:
            if upper_sql.startswith(stmt):
                return stmt

        if upper_sql.startswith("SELECT"):
            return "SELECT"

        # Unknown statement type
        first_word = upper_sql.split()[0] if upper_sql else "EMPTY"
        return first_word

    def _check_injection_patterns(self, sql: str) -> None:
        """Check for SQL injection patterns.

        Args:
            sql: Normalized SQL string

        Raises:
            SQLValidationError: If injection pattern detected
        """
        for pattern, description in self._injection_patterns:
            if pattern.search(sql):
                logger.warning(
                    "SQL injection pattern detected",
                    extra={"pattern": description, "sql_preview": sql[:100]},
                )
                raise SQLValidationError(
                    f"Potentially malicious SQL pattern detected: {description}",
                    error_code="INJECTION_DETECTED",
                    details={"pattern": description},
                )

    def _check_forbidden_objects(self, sql: str) -> None:
        """Check for access to forbidden system objects.

        Args:
            sql: Normalized SQL string

        Raises:
            SQLValidationError: If forbidden object access detected
        """
        upper_sql = sql.upper()

        for obj in self.FORBIDDEN_OBJECTS:
            # Check for direct reference
            pattern = rf"\b{re.escape(obj.upper())}\w*\b"
            if re.search(pattern, upper_sql):
                raise SQLValidationError(
                    f"Access to system object '{obj}' is not allowed",
                    error_code="FORBIDDEN_OBJECT",
                    details={"object": obj},
                )

    def _check_strict_functions(self, sql: str) -> None:
        """Check for forbidden functions in strict mode.

        Args:
            sql: Normalized SQL string

        Raises:
            SQLValidationError: If forbidden function detected
        """
        # Find all function calls
        function_pattern = r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\("
        matches = re.findall(function_pattern, sql, re.IGNORECASE)

        for func_name in matches:
            upper_func = func_name.upper()

            # Check if it's a forbidden function
            if upper_func in self.FORBIDDEN_FUNCTIONS:
                raise SQLValidationError(
                    f"Function '{func_name}' is not allowed",
                    error_code="FORBIDDEN_FUNCTION",
                    details={"function": func_name},
                )

            # In strict mode, only allow explicitly allowed functions
            if (
                self.security_level == SQLSecurityLevel.STRICT
                and upper_func not in self.ALLOWED_FUNCTIONS
                and upper_func not in self.ALLOWED_AGGREGATES
                and upper_func not in {"CASE", "WHEN", "THEN", "ELSE", "END"}
            ):
                raise SQLValidationError(
                    f"Function '{func_name}' is not in the allowed list",
                    error_code="FUNCTION_NOT_ALLOWED",
                    details={
                        "function": func_name,
                        "allowed": list(self.ALLOWED_FUNCTIONS)[:10],
                    },
                )

    def _check_query_complexity(self, sql: str) -> None:
        """Check query complexity limits.

        Args:
            sql: Normalized SQL string

        Raises:
            SQLValidationError: If query exceeds complexity limits
        """
        upper_sql = sql.upper()

        # Count JOINs
        join_count = len(re.findall(r"\bJOIN\b", upper_sql))
        if join_count > self.max_joins:
            raise SQLValidationError(
                f"Query has too many JOINs ({join_count}). Maximum allowed: {self.max_joins}",
                error_code="TOO_MANY_JOINS",
                details={"join_count": join_count, "max_joins": self.max_joins},
            )

        # Count subqueries (approximate by counting SELECT keywords minus 1)
        select_count = len(re.findall(r"\bSELECT\b", upper_sql))
        subquery_count = max(0, select_count - 1)
        if subquery_count > self.max_subqueries:
            raise SQLValidationError(
                f"Query has too many subqueries ({subquery_count}). "
                f"Maximum allowed: {self.max_subqueries}",
                error_code="TOO_MANY_SUBQUERIES",
                details={"subquery_count": subquery_count, "max_subqueries": self.max_subqueries},
            )


def inject_limit(sql: str, max_rows: int) -> tuple[str, int | None]:
    """Inject or adjust LIMIT clause to enforce row limits.

    This function implements the LIMIT+1 strategy for detecting truncation:
    - If query has no LIMIT, adds LIMIT (max_rows + 1)
    - If query has LIMIT > max_rows, replaces with LIMIT (max_rows + 1)
    - If query has LIMIT <= max_rows, keeps original LIMIT

    Args:
        sql: SQL query to modify
        max_rows: Maximum rows to return (will add +1 for truncation detection)

    Returns:
        Tuple of (modified_sql, original_limit or None)
    """
    sql = sql.strip().rstrip(";")

    # Pattern to match LIMIT clause at the end of the query
    # Handles: LIMIT n, LIMIT n OFFSET m
    limit_pattern = re.compile(
        r"\bLIMIT\s+(\d+)(\s+OFFSET\s+\d+)?\s*$",
        re.IGNORECASE,
    )

    match = limit_pattern.search(sql)

    if match:
        original_limit = int(match.group(1))
        offset_clause = match.group(2) or ""

        if original_limit > max_rows:
            # Replace with our limit (+1 for truncation detection)
            new_sql = limit_pattern.sub(f"LIMIT {max_rows + 1}{offset_clause}", sql)
            return new_sql, original_limit
        else:
            # Keep original limit as it's within our threshold
            return sql, original_limit
    else:
        # No LIMIT clause, add one (+1 for truncation detection)
        # Need to insert LIMIT before ORDER BY if present, otherwise at end
        # Actually LIMIT comes after ORDER BY in SQL

        # Check for trailing ORDER BY clause
        # Insert LIMIT at the very end
        new_sql = f"{sql} LIMIT {max_rows + 1}"
        return new_sql, None


def validate_sql(
    sql: str,
    security_level: SQLSecurityLevel = SQLSecurityLevel.STANDARD,
    **kwargs: Any,
) -> SQLValidationResult:
    """Convenience function to validate SQL.

    Args:
        sql: SQL query to validate
        security_level: Security level to apply
        **kwargs: Additional arguments for SQLValidator

    Returns:
        SQLValidationResult

    Raises:
        SQLValidationError: If validation fails
    """
    validator = SQLValidator(security_level=security_level, **kwargs)
    return validator.validate(sql)


def sanitize_identifier(identifier: str) -> str:
    """Sanitize a SQL identifier (table name, column name, etc.).

    Args:
        identifier: The identifier to sanitize

    Returns:
        Sanitized identifier

    Raises:
        SQLValidationError: If identifier is invalid
    """
    # Only allow alphanumeric characters and underscores
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", identifier):
        raise SQLValidationError(
            f"Invalid identifier: {identifier}",
            error_code="INVALID_IDENTIFIER",
            details={"identifier": identifier},
        )

    # Check length
    if len(identifier) > 128:
        raise SQLValidationError(
            "Identifier too long",
            error_code="IDENTIFIER_TOO_LONG",
            details={"length": len(identifier), "max_length": 128},
        )

    return identifier
