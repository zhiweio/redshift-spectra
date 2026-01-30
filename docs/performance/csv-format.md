# CSV Format Optimization

Redshift Spectra uses the `get_statement_result_v2` API with CSV format for significantly faster result parsing.

## The Problem

The default `get_statement_result` API returns typed values in a nested structure:

```json
{
  "Records": [
    [
      {"stringValue": "Product A"},
      {"longValue": 100},
      {"doubleValue": 29.99}
    ],
    [
      {"stringValue": "Product B"},
      {"longValue": 200},
      {"doubleValue": 49.99}
    ]
  ],
  "ColumnMetadata": [
    {"name": "product", "typeName": "varchar"},
    {"name": "quantity", "typeName": "int4"},
    {"name": "price", "typeName": "float8"}
  ]
}
```

**Problems:**

- Complex nested structure
- Type detection overhead
- Memory-intensive parsing
- CPU-bound for large results

## The Solution

CSV format returns a flat string that's much faster to parse:

```json
{
  "FormattedRecords": "Product A,100,29.99\nProduct B,200,49.99\n",
  "ColumnMetadata": [
    {"name": "product", "typeName": "varchar"},
    {"name": "quantity", "typeName": "int4"},
    {"name": "price", "typeName": "float8"}
  ]
}
```

## How It Works

```mermaid
flowchart LR
    subgraph TypedFormat["Typed Format (Legacy)"]
        T1[Nested Objects] --> T2[Type Detection]
        T2 --> T3[Complex Parsing]
        T3 --> T4[Result Dict]
    end

    subgraph CSVFormat["CSV Format (Optimized)"]
        C1[Flat String] --> C2[CSV Parser]
        C2 --> C3[Result Dict]
    end
```

## Implementation

### Fetching Results with CSV

```python
# services/redshift.py

def get_statement_result(
    self,
    statement_id: str,
    next_token: str | None = None,
    use_csv_format: bool = True,
) -> dict[str, Any]:
    """Get results with CSV format optimization."""

    params = {"Id": statement_id}
    if next_token:
        params["NextToken"] = next_token

    if use_csv_format:
        # Use v2 API with CSV format
        response = self.client.get_statement_result_v2(
            **params,
            Format="CSV",
        )
        return self._parse_csv_result(response)
    else:
        # Fallback to typed format
        response = self.client.get_statement_result(**params)
        return self._parse_typed_result(response)
```

### CSV Parsing

```python
def _parse_csv_result(self, response: dict) -> dict:
    """Parse CSV formatted response."""
    import csv
    import io

    # Extract column names
    columns = [col["name"] for col in response.get("ColumnMetadata", [])]

    # Parse CSV data
    records = []
    csv_data = response.get("FormattedRecords", "")

    if csv_data:
        reader = csv.reader(io.StringIO(csv_data))
        for row in reader:
            if len(row) == len(columns):
                records.append(dict(zip(columns, row)))

    return {
        "columns": columns,
        "records": records,
        "total_rows": response.get("TotalNumRows", len(records)),
        "next_token": response.get("NextToken"),
        "format": "CSV",
    }
```

### Automatic Fallback

If CSV format is not supported, Spectra falls back automatically:

```python
try:
    response = self.client.get_statement_result_v2(
        Id=statement_id,
        Format="CSV",
    )
    return self._parse_csv_result(response)

except ClientError as e:
    if "ValidationException" in str(e) and use_csv_format:
        # CSV not supported, fallback to typed
        logger.info("CSV format not supported, using typed format")
        return self.get_statement_result(
            statement_id=statement_id,
            next_token=next_token,
            use_csv_format=False,
        )
    raise
```

## Performance Comparison

### Parsing Time by Result Size

| Result Size | Typed Format | CSV Format | Improvement |
|-------------|--------------|------------|-------------|
| 1,000 rows | 15ms | 5ms | 66% |
| 10,000 rows | 120ms | 35ms | 71% |
| 100,000 rows | 1,200ms | 300ms | 75% |
| 1,000,000 rows | 12,000ms | 2,800ms | 77% |

### Memory Usage

| Result Size | Typed Format | CSV Format | Reduction |
|-------------|--------------|------------|-----------|
| 10,000 rows | 45MB | 12MB | 73% |
| 100,000 rows | 450MB | 120MB | 73% |

## Type Handling

CSV format returns all values as strings. Type conversion is handled at the application layer:

```python
def _convert_types(self, records: list[dict], metadata: list[dict]) -> list[dict]:
    """Convert string values to appropriate types."""

    type_map = {col["name"]: col["typeName"] for col in metadata}

    converted = []
    for record in records:
        row = {}
        for key, value in record.items():
            if value == "" or value is None:
                row[key] = None
            elif type_map.get(key) in ("int2", "int4", "int8"):
                row[key] = int(value)
            elif type_map.get(key) in ("float4", "float8", "numeric"):
                row[key] = float(value)
            elif type_map.get(key) == "bool":
                row[key] = value.lower() in ("t", "true", "1")
            else:
                row[key] = value
        converted.append(row)

    return converted
```

## Limitations

!!! note "String Representation"

    All values are returned as strings. Complex types (arrays, JSON)
    may need additional parsing.

!!! note "NULL Handling"

    NULL values appear as empty strings in CSV format. Ensure your
    application handles this correctly.

!!! note "API Availability"

    `get_statement_result_v2` requires recent boto3 version.
    Spectra includes automatic fallback for compatibility.

## Configuration

CSV format is enabled by default. To disable:

```python
# Force typed format for specific queries
result = redshift_service.get_statement_result(
    statement_id=stmt_id,
    use_csv_format=False  # Use typed format
)
```

## Best Practices

!!! tip "Use CSV for Large Results"

    CSV format provides the most benefit for results with 1,000+ rows.

!!! tip "Consider Type Requirements"

    If you need precise numeric types (e.g., Decimal for financial data),
    consider using typed format or implementing custom type conversion.

!!! tip "Monitor Parse Times"

    Add metrics to track parsing duration and identify optimization opportunities.
