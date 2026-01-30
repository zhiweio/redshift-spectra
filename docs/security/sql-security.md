# SQL Security

SQL injection is one of the most dangerous attack vectors against database systems. Redshift Spectra implements comprehensive SQL validation to prevent malicious queries from reaching your data warehouse.

## Defense in Depth

SQL security in Redshift Spectra is implemented at multiple layers:

```mermaid
flowchart TB
    subgraph Layers["SQL Security Layers"]
        direction TB
        
        subgraph L1["Layer 1: Request Validation"]
            REQ[Request Model<br/>Basic pattern blocking]
        end
        
        subgraph L2["Layer 2: SQL Validator"]
            VAL[Comprehensive Analysis<br/>Pattern matching · Complexity limits]
        end
        
        subgraph L3["Layer 3: Parameterization"]
            PARAM[Parameter Binding<br/>Value separation]
        end
        
        subgraph L4["Layer 4: Database Permissions"]
            PERM[RBAC/RLS<br/>Query execution limits]
        end
    end
    
    SQL[User SQL] --> L1 --> L2 --> L3 --> L4 --> RS[(Redshift)]
```

Even if an attacker bypasses one layer, others continue to protect your data.

## SQL Validator

The SQL Validator is the primary defense against SQL injection and query abuse. It analyzes queries before execution using multiple techniques.

### Security Levels

Three security levels are available, each with different trade-offs:

```mermaid
flowchart LR
    subgraph Levels["Security Levels"]
        direction TB
        
        STRICT["STRICT<br/>━━━━━━━━<br/>• SELECT only<br/>• No subqueries<br/>• No CTEs<br/>• Minimal functions"]
        
        STANDARD["STANDARD<br/>━━━━━━━━<br/>• SELECT only<br/>• Subqueries allowed<br/>• CTEs allowed<br/>• Safe functions"]
        
        PERMISSIVE["PERMISSIVE<br/>━━━━━━━━<br/>• SELECT only<br/>• All subqueries<br/>• All CTEs<br/>• More functions"]
    end
    
    STRICT -.->|"More restrictive"| STANDARD -.->|"Less restrictive"| PERMISSIVE
```

| Level | Use Case | Query Complexity |
|-------|----------|------------------|
| **STRICT** | Untrusted external users | Simple queries only |
| **STANDARD** | Internal applications | Most analytical queries |
| **PERMISSIVE** | Trusted data engineers | Complex analytical queries |

### Blocked Patterns

The validator blocks dangerous SQL patterns regardless of security level:

```mermaid
flowchart TB
    subgraph Blocked["❌ Always Blocked"]
        direction TB
        
        DDL["DDL Statements<br/>DROP, CREATE, ALTER, TRUNCATE"]
        DML["DML Statements<br/>INSERT, UPDATE, DELETE"]
        ADMIN["Admin Operations<br/>GRANT, REVOKE, COPY"]
        SYSTEM["System Access<br/>pg_catalog, stl_*, stv_*"]
        DANGEROUS["Dangerous Functions<br/>pg_read_file, pg_terminate"]
    end
    
    SQL[User SQL] --> CHECK{Contains Blocked Pattern?}
    CHECK -->|Yes| REJECT[Reject with Error]
    CHECK -->|No| CONTINUE[Continue Validation]
```

### Pattern Detection

The validator uses multiple detection techniques:

**1. Statement Type Detection**

Only SELECT statements (and WITH...SELECT for CTEs) are allowed:

```mermaid
flowchart LR
    SQL[Query] --> PARSE[Parse First Token]
    PARSE --> CHECK{SELECT or WITH?}
    CHECK -->|No| DENY[Deny]
    CHECK -->|Yes| ALLOW[Allow]
```

**2. Dangerous Pattern Matching**

Regular expressions detect dangerous patterns:

| Category | Patterns Blocked |
|----------|-----------------|
| DDL | `DROP TABLE`, `CREATE TABLE`, `ALTER TABLE` |
| DML | `INSERT INTO`, `UPDATE SET`, `DELETE FROM` |
| Stacked queries | `; DROP`, `; DELETE`, `; INSERT` |
| Comment injection | `/*...*/DROP`, `--...DELETE` |
| System tables | `pg_catalog.`, `information_schema.` |
| Hex encoding | `0x44524f50` (encoded DROP) |

**3. Complexity Analysis**

Queries are analyzed for complexity to prevent resource abuse:

```mermaid
flowchart TB
    SQL[Query] --> ANALYZE[Analyze Complexity]
    
    ANALYZE --> JOINS{JOIN count > limit?}
    JOINS -->|Yes| DENY1[Deny: Too many JOINs]
    JOINS -->|No| SUBQ{Subquery depth > limit?}
    
    SUBQ -->|Yes| DENY2[Deny: Too many subqueries]
    SUBQ -->|No| LENGTH{Query length > limit?}
    
    LENGTH -->|Yes| DENY3[Deny: Query too long]
    LENGTH -->|No| ALLOW[Allow]
```

### Complexity Limits

| Limit | Default | Purpose |
|-------|---------|---------|
| Max JOINs | 10 | Prevent expensive cross-joins |
| Max Subqueries | 5 | Limit query complexity |
| Max Query Length | 100KB | Prevent buffer overflow |
| Max UNION clauses | 0 (blocked) | Prevent result set manipulation |

## LIMIT Enforcement

The Query API automatically enforces result limits to prevent memory exhaustion:

```mermaid
flowchart TB
    subgraph LimitLogic["LIMIT Injection Logic"]
        direction TB
        
        Q1["Query without LIMIT"] --> ADD["Add LIMIT (threshold+1)"]
        Q2["Query with LIMIT > threshold"] --> REPLACE["Replace with LIMIT (threshold+1)"]
        Q3["Query with LIMIT <= threshold"] --> KEEP["Keep original LIMIT"]
    end
    
    subgraph Detection["Truncation Detection"]
        direction TB
        
        EXEC["Execute Query"] --> CHECK{Rows > threshold?}
        CHECK -->|Yes| TRUNCATE["Truncate to threshold<br/>Set truncated=true"]
        CHECK -->|No| RETURN["Return all rows"]
    end
    
    LimitLogic --> Detection
```

The LIMIT+1 strategy allows detection of truncation without executing the query twice.

## Parameter Binding

Parameterized queries separate SQL structure from data values:

```mermaid
flowchart TB
    subgraph Vulnerable["❌ String Concatenation"]
        %% 使用 #quot; 代替内部的双引号
        BAD["SELECT * FROM users WHERE id = '#quot; + user_input + #quot;'"]
        ATTACK["user_input = ' OR 1=1 --"]
        RESULT1["SELECT * FROM users WHERE id = '' OR 1=1 --'"]
    end
    
    subgraph Safe["✅ Parameter Binding"]
        GOOD["SELECT * FROM users WHERE id = :user_id"]
        PARAM["user_id = ' OR 1=1 --"]
        RESULT2["Parameter treated as literal string<br/>No injection possible"]
    end
```

Use parameters for any user-provided values:

| Parameter Type | Supported |
|---------------|-----------|
| String | ✓ |
| Integer | ✓ |
| Float | ✓ |
| Boolean | ✓ |
| Null | ✓ |
| Date/Time | ✓ (as string) |

## Attack Prevention Examples

### SQL Injection Attempts

```mermaid
flowchart TB
    subgraph Attacks["Attack Attempts"]
        A1["SELECT * FROM users; DROP TABLE users"]
        A2["SELECT * FROM users WHERE 1=1 --"]
        A3["SELECT * FROM users UNION SELECT * FROM secrets"]
        A4["SELECT * FROM pg_catalog.pg_user"]
    end
    
    subgraph Detection["Detection & Response"]
        D1["Stacked query detected"] --> DENY1[403 Forbidden]
        D2["Comment injection detected"] --> DENY2[403 Forbidden]
        D3["UNION not allowed"] --> DENY3[403 Forbidden]
        D4["System table access blocked"] --> DENY4[403 Forbidden]
    end
    
    A1 --> D1
    A2 --> D2
    A3 --> D3
    A4 --> D4
```

### Real-World Attack Patterns

| Attack | Detection Method | Response |
|--------|-----------------|----------|
| `'; DROP TABLE --` | Stacked query pattern | Blocked |
| `UNION SELECT password FROM users` | UNION pattern | Blocked |
| `' OR '1'='1` | Parameterization prevents | No effect |
| `0x44524f50205441424c45` | Hex encoding detection | Blocked |
| `SELECT * FROM stl_query` | System table pattern | Blocked |

## Validation Response

When validation fails, detailed error information is returned:

```mermaid
flowchart TB
    FAIL[Validation Failed] --> ERROR[Error Response]
    
    ERROR --> CODE["error_code:<br/>FORBIDDEN_STATEMENT"]
    ERROR --> MSG["message:<br/>SQL contains forbidden pattern: DROP"]
    ERROR --> DETAILS["details:<br/>pattern_matched, position"]
```

Error codes:

| Code | Description |
|------|-------------|
| `FORBIDDEN_STATEMENT` | Blocked statement type detected |
| `FORBIDDEN_PATTERN` | Dangerous pattern detected |
| `COMPLEXITY_EXCEEDED` | Query too complex |
| `EMPTY_QUERY` | No SQL provided |
| `SYSTEM_TABLE_ACCESS` | Attempt to access system tables |

## Best Practices

!!! tip "Always Use Parameters"
    Never concatenate user input into SQL strings:
    
    - Use named parameters (`:param_name`)
    - Let the validator handle escaping
    - Audit parameter usage in logs

!!! tip "Start with STRICT Mode"
    For external-facing APIs:
    
    - Begin with STRICT security level
    - Relax only if specific queries require it
    - Document why relaxation is needed

!!! warning "Monitor Validation Failures"
    High validation failure rates may indicate:
    
    - Attack attempts in progress
    - Misconfigured client applications
    - Need for user education

!!! info "Validation is Not a Replacement"
    SQL validation complements, but doesn't replace:
    
    - Row-Level Security (data isolation)
    - RBAC (permission control)
    - Parameter binding (injection prevention)

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `SPECTRA_SQL_SECURITY_LEVEL` | `standard` | Security level: strict, standard, permissive |
| `SPECTRA_SQL_MAX_QUERY_LENGTH` | `100000` | Maximum query length in characters |
| `SPECTRA_SQL_MAX_JOINS` | `10` | Maximum JOIN clauses |
| `SPECTRA_SQL_MAX_SUBQUERIES` | `5` | Maximum subquery depth |
| `SPECTRA_SQL_ALLOW_CTE` | `true` | Allow WITH clauses (CTEs) |
| `SPECTRA_SQL_ALLOW_UNION` | `false` | Allow UNION (disabled by default) |

## Audit Trail

All SQL validation events are logged:

- **Passed validations** — With normalized SQL and warnings
- **Failed validations** — With error code and matched pattern
- **Complexity metrics** — JOIN count, subquery depth, query length
