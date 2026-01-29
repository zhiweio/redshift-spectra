# Authentication

Redshift Spectra supports multiple authentication modes to integrate with your existing identity infrastructure.

## Authentication Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AG as API Gateway
    participant AUTH as Lambda Authorizer
    participant SM as Secrets Manager
    participant H as Handler

    C->>AG: Request + Credentials
    AG->>AUTH: Invoke Authorizer
    
    alt API Key
        AUTH->>SM: Validate API Key
        SM-->>AUTH: Key Metadata
    else JWT
        AUTH->>AUTH: Validate Signature
        AUTH->>AUTH: Check Claims
    else IAM
        AG->>AG: SigV4 Validation
    end
    
    AUTH-->>AG: IAM Policy + Context
    AG->>H: Forward Request
```

## Supported Modes

### API Key Authentication

Best for machine-to-machine communication.

**Configuration:**

```bash
SPECTRA_AUTH_MODE=api_key
```

**Usage:**

```bash
curl -X POST "$API_URL/queries" \
  -H "Authorization: Bearer spectra_tenant123_abc123xyz" \
  -H "X-Tenant-ID: tenant-123"
```

**Key Format:**

```
spectra_{tenant_id}_{secret_hash}
```

**Benefits:**

- Simple integration
- No token refresh needed
- Easy to rotate

**Considerations:**

- Must be kept secret
- Harder to audit per-user access
- Consider expiration policies

### JWT Authentication

Best for user-facing applications with identity providers.

**Configuration:**

```bash
SPECTRA_AUTH_MODE=jwt
SPECTRA_JWT_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:jwt/secret
SPECTRA_JWT_ISSUER=https://auth.example.com
SPECTRA_JWT_AUDIENCE=spectra-api
```

**Usage:**

```bash
curl -X POST "$API_URL/queries" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIs..."
```

**Expected Claims:**

```json
{
  "sub": "user-123",
  "iss": "https://auth.example.com",
  "aud": "spectra-api",
  "exp": 1738234800,
  "tenant_id": "tenant-123",
  "db_user": "tenant_123",
  "permissions": ["query", "export"]
}
```

**Supported Algorithms:**

- RS256, RS384, RS512 (RSA)
- ES256, ES384, ES512 (ECDSA)
- HS256, HS384, HS512 (HMAC)

### IAM Authentication

Best for AWS service-to-service communication.

**Configuration:**

```bash
SPECTRA_AUTH_MODE=iam
```

**Usage:**

```python
import boto3
from requests_aws4auth import AWS4Auth

session = boto3.Session()
credentials = session.get_credentials()
auth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    'us-east-1',
    'execute-api',
    session_token=credentials.token
)

response = requests.post(
    f"{API_URL}/queries",
    auth=auth,
    headers={"X-Tenant-ID": "tenant-123"},
    json={"sql": "SELECT 1"}
)
```

## Tenant Context Extraction

The authorizer extracts tenant context from multiple sources:

```mermaid
flowchart TB
    REQ[Request] --> H{Headers?}
    H -->|X-Tenant-ID| HEADER[Header Tenant]
    H -->|No| T{Token?}
    
    T -->|JWT Claims| CLAIMS[Token Tenant]
    T -->|API Key| PARSE[Parse Key]
    
    HEADER --> CTX[Tenant Context]
    CLAIMS --> CTX
    PARSE --> CTX
    
    CTX --> DBUSER[Map to db_user]
```

### Priority Order

1. `X-Tenant-ID` header (highest priority)
2. JWT claim `tenant_id` or `custom:tenant_id`
3. Derived from API key ID

## Lambda Authorizer

The authorizer returns an IAM policy and context:

```json
{
  "principalId": "tenant-123",
  "policyDocument": {
    "Version": "2012-10-17",
    "Statement": [{
      "Action": "execute-api:Invoke",
      "Effect": "Allow",
      "Resource": "arn:aws:execute-api:us-east-1:*:*/*/queries/*"
    }]
  },
  "context": {
    "tenant_id": "tenant-123",
    "db_user": "tenant_123",
    "db_group": "tenant_group_123",
    "permissions": "query,export"
  }
}
```

## Token Refresh

For JWT authentication, implement token refresh in your client:

```python
class SpectraClient:
    def __init__(self, auth_url, client_id, client_secret):
        self.auth_url = auth_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expiry = None
    
    def get_token(self):
        if self.token and datetime.now() < self.token_expiry:
            return self.token
        
        response = requests.post(
            f"{self.auth_url}/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
        )
        
        data = response.json()
        self.token = data["access_token"]
        self.token_expiry = datetime.now() + timedelta(seconds=data["expires_in"] - 60)
        
        return self.token
```

## Security Best Practices

!!! tip "Use Short-Lived Tokens"
    
    For JWT, use short expiration times (15-60 minutes) with refresh tokens.

!!! tip "Rotate API Keys"
    
    Implement regular API key rotation. Use Secrets Manager for storage.

!!! warning "Never Log Credentials"
    
    Ensure logging excludes Authorization headers and tokens.

!!! danger "Validate All Inputs"
    
    Never trust client-provided tenant IDs without validation against credentials.
