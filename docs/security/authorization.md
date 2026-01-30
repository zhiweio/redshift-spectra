# Authorization

After authentication establishes identity, authorization determines what actions a user can perform and what data they can access. Redshift Spectra implements authorization at two levels: the **API layer** and the **database layer**.

## Authorization Architecture

```mermaid
flowchart TB
    subgraph APILayer["API Layer Authorization"]
        direction LR
        PERM[Permission Check] --> |"query:execute"| ALLOW1[Allow]
        PERM --> |"bulk:create"| ALLOW2[Allow]
        PERM --> |"missing"| DENY[Deny 403]
    end
    
    subgraph DBLayer["Database Layer Authorization"]
        direction LR
        USER[db_user] --> RBAC[Role-Based Access]
        RBAC --> RLS[Row-Level Security]
        RLS --> DATA[Filtered Data]
    end
    
    REQUEST[Request + Tenant Context] --> APILayer
    APILayer --> |"Allowed"| DBLayer
```

## API Layer Authorization

The API layer checks whether the authenticated user has permission to perform the requested operation.

### Permission Model

Permissions are strings that describe allowed operations:

| Permission | Description | Scope |
|------------|-------------|-------|
| `query:execute` | Submit synchronous queries | Query API |
| `bulk:create` | Create bulk export/import jobs | Bulk API |
| `bulk:read` | Read job status and results | Bulk API |
| `bulk:cancel` | Cancel running jobs | Bulk API |
| `admin:*` | All administrative operations | Admin API |
| `*` | Wildcard (all permissions) | All APIs |

### Permission Sources

Permissions can come from multiple sources:

```mermaid
flowchart TB
    subgraph Sources["Permission Sources"]
        JWT[JWT Claims<br/>permissions: [...]]
        LOOKUP[API Key Lookup<br/>tenant_permissions table]
        DEFAULT[Default Permissions<br/>query:execute, bulk:read]
    end
    
    Sources --> MERGE[Merge Permissions]
    MERGE --> CHECK[Permission Check]
```

### Permission Hierarchy

Permissions support hierarchical matching:

- `bulk:*` matches `bulk:create`, `bulk:read`, `bulk:cancel`
- `*` matches all permissions
- Exact match is required otherwise

```mermaid
flowchart LR
    REQ[Required: bulk:create] --> CHECK{Permission Check}
    
    CHECK --> |"Has: bulk:create"| EXACT[Exact Match ✓]
    CHECK --> |"Has: bulk:*"| WILD[Wildcard Match ✓]
    CHECK --> |"Has: *"| ALL[Universal Match ✓]
    CHECK --> |"Has: query:execute"| DENY[No Match ✗]
```

### Permission Enforcement

Permission checks happen after authentication but before business logic:

```mermaid
sequenceDiagram
    participant H as Handler
    participant D as Decorator
    participant L as Logic
    
    H->>D: @require_permission("bulk:create")
    D->>D: Check tenant_context.permissions
    
    alt Has Permission
        D->>L: Execute Business Logic
        L-->>H: Result
    else Missing Permission
        D-->>H: 403 Forbidden
    end
```

## Database Layer Authorization

The database layer controls what data the user can access. This is the **critical security boundary** that guarantees tenant isolation.

### Role-Based Access Control (RBAC)

Each database user belongs to groups that determine their base permissions:

```mermaid
flowchart TB
    subgraph Users["Database Users"]
        U1[db_user_acme]
        U2[db_user_globex]
        U3[db_user_initech]
    end
    
    subgraph Groups["Database Groups"]
        G1[tenant_readers<br/>SELECT on views]
        G2[tenant_writers<br/>SELECT, INSERT on views]
        G3[tenant_admins<br/>Full access to tenant objects]
    end
    
    subgraph Objects["Database Objects"]
        V1[sales_view]
        V2[customers_view]
        V3[analytics_view]
    end
    
    U1 --> G1
    U2 --> G2
    U3 --> G1
    
    G1 --> V1
    G1 --> V2
    G2 --> V1
    G2 --> V2
    G2 --> V3
```

### Row-Level Security (RLS)

RLS policies automatically filter data based on the executing user:

```mermaid
flowchart TB
    subgraph Query["User Query"]
        Q1["SELECT * FROM orders"]
    end
    
    subgraph RLS["RLS Policy"]
        POLICY["WHERE tenant_id = CURRENT_USER_ID()"]
    end
    
    subgraph Execution["Actual Execution"]
        ACTUAL["SELECT * FROM orders<br/>WHERE tenant_id = 'acme-corp'"]
    end
    
    subgraph Result["Result Set"]
        DATA["Only ACME Corp orders"]
    end
    
    Query --> RLS
    RLS --> Execution
    Execution --> Result
```

This means:

- The same SQL query works for all tenants
- No application code changes needed
- Impossible to accidentally access other tenant's data

### Setting Up RLS in Redshift

Row-Level Security requires creating policies in Redshift:

```mermaid
flowchart TB
    subgraph Setup["RLS Setup Steps"]
        direction TB
        S1["1. Enable RLS on table"]
        S2["2. Create RLS policy"]
        S3["3. Attach policy to group"]
        S4["4. Grant group to user"]
    end
    
    S1 --> S2 --> S3 --> S4
```

**Key concepts:**

1. **Tables must have a tenant identifier column** — Usually `tenant_id`
2. **Policies match column to user context** — `tenant_id = CURRENT_USER`
3. **Policies apply automatically** — No query modification needed
4. **Superusers bypass RLS** — Use dedicated users, not admin accounts

## Column-Level Security

Beyond row filtering, Redshift supports column-level access control:

```mermaid
flowchart LR
    subgraph Columns["Table Columns"]
        C1[id]
        C2[name]
        C3[email]
        C4[ssn]
        C5[salary]
    end
    
    subgraph Access["Access Levels"]
        PUBLIC[All Users]
        LIMITED[Analysts]
        RESTRICTED[Admins Only]
    end
    
    C1 --> PUBLIC
    C2 --> PUBLIC
    C3 --> LIMITED
    C4 --> RESTRICTED
    C5 --> RESTRICTED
```

This ensures sensitive columns like PII are only visible to authorized users.

## Authorization Decision Flow

The complete authorization flow:

```mermaid
flowchart TB
    REQUEST[Incoming Request] --> AUTHN{Authenticated?}
    
    AUTHN -->|No| DENY401[401 Unauthorized]
    AUTHN -->|Yes| PERM{Has Permission?}
    
    PERM -->|No| DENY403[403 Forbidden]
    PERM -->|Yes| EXECUTE[Execute Query]
    
    EXECUTE --> RBAC{RBAC Check}
    
    RBAC -->|Denied| ERROR[Query Error]
    RBAC -->|Allowed| RLS[Apply RLS]
    
    RLS --> RESULT[Filtered Results]
```

## Tenant Isolation Verification

To verify tenant isolation is working correctly:

```mermaid
flowchart TB
    subgraph Test["Isolation Test"]
        T1[Connect as tenant_a user]
        T2[Query shared table]
        T3[Verify only tenant_a data]
        
        T1 --> T2 --> T3
    end
    
    subgraph Expected["Expected Behavior"]
        E1[Query: SELECT COUNT(*) FROM orders]
        E2[Result: 1000 rows<br/>All belong to tenant_a]
    end
    
    Test --> Expected
```

## Best Practices

!!! tip "Principle of Least Privilege"
    Grant the minimum permissions required:
    
    - Start with `query:execute` only
    - Add permissions as needed
    - Use specific permissions over wildcards

!!! tip "Use Database Groups"
    Don't grant permissions directly to users:
    
    - Create logical groups (readers, writers, admins)
    - Grant permissions to groups
    - Add users to groups

!!! warning "Test Tenant Isolation"
    Regularly verify that RLS is working:
    
    - Create test tenants with known data
    - Verify cross-tenant queries return no data
    - Include in CI/CD pipeline

!!! danger "Never Use Superuser Connections"
    Superusers bypass all RLS policies:
    
    - Create dedicated application users
    - Use Secrets Manager for credential rotation
    - Monitor for superuser access

## Error Responses

| Error | HTTP Status | Description |
|-------|-------------|-------------|
| Missing permission | 403 | User lacks required API permission |
| Invalid operation | 403 | Operation not allowed for this tenant |
| RLS violation | 500 | Query fails due to RLS restriction |

## Audit Trail

All authorization decisions are logged:

- **API permission checks** — Logged with outcome and required permission
- **Database access** — Logged in Redshift audit logs
- **RLS applications** — Visible in query explain plans
