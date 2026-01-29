# Security Overview

Redshift Spectra implements a **zero-trust security model** with defense-in-depth across all layers.

## Security Architecture

```mermaid
flowchart TB
    subgraph Client["Client Layer"]
        APP[Application]
    end
    
    subgraph Edge["Edge Security"]
        WAF[AWS WAF]
        APIGW[API Gateway]
    end
    
    subgraph Auth["Authentication"]
        AUTHZ[Lambda Authorizer]
        JWT[JWT Validation]
        APIKEY[API Key Validation]
    end
    
    subgraph Tenant["Tenant Isolation"]
        CONTEXT[Tenant Context]
        DBUSER[Database User Mapping]
    end
    
    subgraph Data["Data Security"]
        RLS[Row-Level Security]
        CLS[Column-Level Security]
        ENCRYPT[Encryption]
    end
    
    APP --> WAF
    WAF --> APIGW
    APIGW --> AUTHZ
    AUTHZ --> JWT
    AUTHZ --> APIKEY
    AUTHZ --> CONTEXT
    CONTEXT --> DBUSER
    DBUSER --> RLS
    DBUSER --> CLS
    RLS --> ENCRYPT
```

## Security Layers

### 1. Edge Security

**AWS WAF** provides protection against:

- SQL injection attempts
- Cross-site scripting (XSS)
- Rate limiting
- Bot mitigation
- Geographic restrictions

**API Gateway** provides:

- TLS termination
- Request validation
- Throttling
- API key management

### 2. Authentication

Multiple authentication modes supported:

| Mode | Use Case | Token Lifetime |
|------|----------|----------------|
| API Key | Machine-to-machine | Long-lived |
| JWT | User authentication | Short-lived |
| IAM | AWS service calls | Temporary |

### 3. Tenant Isolation

Every request is associated with a tenant context:

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Authorizer
    participant H as Handler
    participant R as Redshift

    C->>A: Request + Credentials
    A->>A: Validate & Extract Tenant
    A->>H: Policy + Tenant Context
    H->>H: Map Tenant → db_user
    H->>R: Execute as db_user
    R->>R: Apply RLS/CLS
    R-->>C: Filtered Results
```

### 4. Data Security

**Row-Level Security (RLS):**

Tenants only see their own data:

```sql
CREATE RLS POLICY tenant_isolation
ON sales
USING (tenant_id = current_user);
```

**Column-Level Security (CLS):**

Restrict sensitive columns:

```sql
REVOKE SELECT (ssn, credit_card)
ON customers
FROM tenant_group;
```

**Encryption:**

- Data at rest: AES-256
- Data in transit: TLS 1.2+
- S3 exports: Server-side encryption

## Compliance Considerations

| Standard | Relevant Features |
|----------|-------------------|
| **SOC 2** | Audit logging, access controls, encryption |
| **GDPR** | Data isolation, encryption, right to access |
| **HIPAA** | PHI protection, access controls, audit trails |
| **PCI DSS** | Encryption, access logging, network isolation |

## Security Checklist

=== "Development"

    - [ ] Use non-production credentials
    - [ ] Enable all logging
    - [ ] Test RLS policies work correctly
    - [ ] Validate input sanitization

=== "Production"

    - [ ] Enable AWS WAF
    - [ ] Configure VPC endpoints
    - [ ] Set up CloudTrail
    - [ ] Enable GuardDuty
    - [ ] Configure SNS alerts
    - [ ] Regular credential rotation

## Threat Model

| Threat | Mitigation |
|--------|------------|
| SQL Injection | Parameterized queries, input validation |
| Credential Theft | Short-lived tokens, Secrets Manager |
| Data Leakage | RLS, CLS, encryption |
| Privilege Escalation | Least-privilege IAM, database roles |
| DDoS | WAF, API throttling, rate limiting |
| Insider Threat | Audit logging, principle of least privilege |

## Next Steps

- [Authentication](authentication.md) - Deep dive into auth modes
- [Authorization](authorization.md) - RLS and CLS implementation
