# Calpendo API Contract

**Feature**: 002-calpendo-plugin  
**API Version**: WebDAV Query Interface  
**Base URL**: `https://sfc-calgary.calpendo.com` (configurable)  
**Authentication**: HTTP Basic Auth

---

## Authentication

**Method**: HTTP Basic Authentication  
**Headers**:
```http
Authorization: Basic {base64(username:password)}
```

**Credentials** (from environment):
```bash
CALPENDO_USERNAME=your_username
CALPENDO_PASSWORD=your_password
```

**Error Responses**:
- `401 Unauthorized`: Invalid credentials
- `403 Forbidden`: Insufficient permissions

---

## Endpoints

### 1. Query Bookings

**Purpose**: Fetch bookings matching query criteria (date range, resources, etc.)

**Endpoint**:
```
GET {base_url}/webdav/q/Calpendo.Booking/{query}
```

**Query Syntax**:

Calpendo uses URL path-based query language with boolean operators and field comparisons.

**Date Range** (required for plugin):
```
AND/dateRange.start/GE/{start_date}/dateRange.start/LT/{end_date}
```
- `AND`: Boolean operator (all conditions must match)
- `dateRange.start`: Booking start time field
- `GE`: Greater than or equal to
- `LT`: Less than
- Date format: `YYYYMMDD-HHMM` (e.g., `20250212-1000`)

**Resource Filter** (optional):
```
OR/resource.name/EQ/{resource1}/resource.name/EQ/{resource2}
```
- `OR`: Boolean operator (any condition can match)
- `resource.name`: Scanner/equipment name
- `EQ`: Equals (exact match)
- Values: URL-encoded resource names

**Combined Example**:
```
GET https://sfc-calgary.calpendo.com/webdav/q/Calpendo.Booking/AND/dateRange.start/GE/20250212-1000/dateRange.start/LT/20250212-1800/OR/resource.name/EQ/3T%20Diagnostic/resource.name/EQ/EEG
```

**Response** (200 OK):
```json
{
  "biskits": [
    {
      "id": 12345,
      "formattedName": "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]",
      "title": "SUB001 - John Doe",
      "status": "Approved",
      "biskitType": "MRIScan",
      "created": "2025-02-03T20:18Z"
    },
    {
      "id": 12346,
      "formattedName": "[2025-02-12 14:00:00.0, 2025-02-12 15:00:00.0]",
      "title": "SUB002 - Jane Smith",
      "status": "Pending",
      "biskitType": "EEGScan",
      "created": "2025-02-10T15:30Z"
    }
  ]
}
```

**Response Fields**:
- `biskits`: Array of booking objects
- `id`: Unique booking identifier
- `formattedName`: Date/time range string (Mountain Time)
- `title`: Subject identifier (may contain patient info)
- `status`: Booking status (Approved, Pending, Cancelled, etc.)
- `biskitType`: Booking type (MRIScan, EEGScan, etc.)
- `created`: Creation timestamp (ISO 8601 UTC)

**Error Responses**:
- `400 Bad Request`: Invalid query syntax
- `500 Internal Server Error`: Calpendo service error

---

### 2. Get Booking Details

**Purpose**: Fetch complete booking information including nested properties

**Endpoint**:
```
GET {base_url}/webdav/b/Calpendo.Booking/{booking_id}
```

**Example**:
```
GET https://sfc-calgary.calpendo.com/webdav/b/Calpendo.Booking/12345
Authorization: Basic dXNlcjpwYXNz
```

**Response** (200 OK):
```json
{
  "id": 12345,
  "formattedName": "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]",
  "title": "SUB001 - John Doe",
  "status": "Approved",
  "biskitType": "MRIScan",
  "created": "2025-02-03T20:18Z",
  "properties": {
    "resource": {
      "formattedName": "3T Diagnostic",
      "id": 789,
      "name": "3T Diagnostic"
    },
    "project": {
      "formattedName": "BRISKP (Brain network models for understanding Risk)",
      "id": 456,
      "name": "BRISKP"
    },
    "booker": {
      "formattedName": "Dr. Emily Smith",
      "id": 101
    },
    "owner": {
      "formattedName": "Dr. Robert Jones",
      "id": 102
    },
    "durationInMinutes": 60,
    "created": "2025-02-03T20:18Z",
    "modified": "2025-02-04T10:30Z",
    "description": "T1 weighted anatomical scan",
    "cancelled": false,
    "cancellationReason": null
  }
}
```

**Properties Fields**:
- `resource`: Scanner/equipment details
  - `formattedName`: Display name (e.g., "3T Diagnostic")
  - `id`: Resource identifier
- `project`: Study/research project
  - `formattedName`: Project name with description
  - `id`: Project identifier
- `booker`: Person who created the booking
- `owner`: Booking owner (may differ from booker)
- `durationInMinutes`: Booking duration
- `modified`: Last modification timestamp (ISO 8601 UTC)
- `description`: Optional booking notes
- `cancelled`: Boolean cancellation flag
- `cancellationReason`: Text reason if cancelled

**Error Responses**:
- `404 Not Found`: Booking ID doesn't exist

---

### 3. Get Extended Details (MRIScan only)

**Purpose**: Fetch additional fields for MRI bookings (operator info, staff confirmation)

**Endpoint**:
```
GET {base_url}/webdav/q/{biskitType}/id/eq/{booking_id}?paths={field1},{field2},...
```

**Example**:
```
GET https://sfc-calgary.calpendo.com/webdav/q/MRIScan/id/eq/12345?paths=resource.name,Operator.name,staffConformation
Authorization: Basic dXNlcjpwYXNz
```

**Query Parameters**:
- `paths`: Comma-separated list of fields to retrieve

**Response** (200 OK):
```json
{
  "biskits": [
    {
      "id": 12345,
      "resource.name": "3T Diagnostic",
      "Operator.name": {
        "formattedName": "Jane Smith",
        "id": 201
      },
      "staffConformation": "Confirmed"
    }
  ]
}
```

**Extended Fields**:
- `Operator.name`: MRI operator assigned to scan
- `staffConformation`: Staff confirmation status
- `resource.name`: Resource name (redundant, available in basic details)

**Notes**:
- Only works for `MRIScan` biskitType
- Other booking types (EEGScan, etc.) don't have Operator field
- Operator may be hidden (`"<Hidden>"`) depending on permissions

**Error Responses**:
- `404 Not Found`: Booking ID doesn't exist or not an MRIScan

---

## Query Examples

### Fetch Today's Bookings (All Resources)

**Query**:
```
AND/dateRange.start/GE/20260127-0000/dateRange.start/LT/20260128-0000
```

**Full URL**:
```
GET https://sfc-calgary.calpendo.com/webdav/q/Calpendo.Booking/AND/dateRange.start/GE/20260127-0000/dateRange.start/LT/20260128-0000
```

---

### Fetch Next 24 Hours (3T Scanner Only)

**Query**:
```
AND/dateRange.start/GE/20260127-1030/dateRange.start/LT/20260128-1030/resource.name/EQ/3T%20Diagnostic
```

**Full URL**:
```
GET https://sfc-calgary.calpendo.com/webdav/q/Calpendo.Booking/AND/dateRange.start/GE/20260127-1030/dateRange.start/LT/20260128-1030/resource.name/EQ/3T%20Diagnostic
```

---

### Fetch Multiple Resources

**Query**:
```
AND/dateRange.start/GE/20260127-0800/dateRange.start/LT/20260127-1800/OR/resource.name/EQ/3T%20Diagnostic/resource.name/EQ/EEG/resource.name/EQ/Mock%20Scanner
```

**Full URL**:
```
GET https://sfc-calgary.calpendo.com/webdav/q/Calpendo.Booking/AND/dateRange.start/GE/20260127-0800/dateRange.start/LT/20260127-1800/OR/resource.name/EQ/3T%20Diagnostic/resource.name/EQ/EEG/resource.name/EQ/Mock%20Scanner
```

---

## Rate Limiting

**Observed Behavior**:
- No documented rate limits
- Conservative approach: max 5 concurrent requests (ThreadPoolExecutor max_workers=5)
- Request timeout: 30 seconds

**Recommendations**:
- Use parallel requests for booking detail fetching (50 bookings → ~10s with 5 workers)
- Implement exponential backoff for 5xx errors
- Cache results within sync cycle to avoid duplicate requests

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Plugin Action |
|------|---------|---------------|
| `200` | Success | Process response |
| `400` | Bad Request (invalid query) | Raise PluginConfigError |
| `401` | Unauthorized (invalid credentials) | Raise PluginConfigError |
| `403` | Forbidden (insufficient permissions) | Raise PluginConfigError |
| `404` | Not Found (booking deleted) | Log warning, skip booking |
| `500` | Internal Server Error | Retry with backoff, then raise PluginFetchError |
| `503` | Service Unavailable | Retry with backoff, then raise PluginFetchError |

### Retry Strategy

**Transient Errors** (500, 503, connection errors):
```python
max_retries = 3
for attempt in range(max_retries):
    try:
        response = requests.get(url, auth=auth, timeout=30)
        response.raise_for_status()
        return response.json()
    except (requests.ConnectionError, requests.Timeout) as e:
        if attempt < max_retries - 1:
            sleep_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
            logger.warning(f"Retry {attempt+1}/{max_retries} after {sleep_time}s: {e}")
            time.sleep(sleep_time)
        else:
            raise PluginFetchError(f"Failed after {max_retries} attempts: {e}")
```

**Permanent Errors** (401, 400):
- No retry
- Raise PluginConfigError immediately
- Stops sync cycle (requires configuration fix)

---

## API Limitations

### No Modification Timestamp Queries

**Problem**: Cannot query bookings modified since last sync

**Impact**: Must fetch all bookings in date range, even if unchanged

**Mitigation**: 
- Use rolling window (fetch last N hours)
- Implement local change detection (hash critical fields)
- Only write to DB when changes detected

### No Deletion Events

**Problem**: No API to detect deleted bookings

**Impact**: Must compare fetch results with DB to find missing bookings

**Mitigation**:
- Track fetched booking IDs
- Compare with existing DB records
- Mark missing bookings as DISCONTINUED

### No Status Change Notifications

**Problem**: No webhook or push notifications for booking changes

**Impact**: Polling only (periodic sync)

**Mitigation**:
- Configurable sync interval (e.g., 5 minutes)
- Sufficient for worklist use case (bookings created hours/days in advance)

---

## Response Time Benchmarks

**Query Bookings** (1-day range, 3 resources):
- Latency: ~500ms
- Response size: ~5KB (10 bookings)

**Get Booking Details** (single booking):
- Latency: ~200ms
- Response size: ~2KB

**Parallel Detail Fetch** (50 bookings, 5 workers):
- Total time: ~10s
- vs Sequential: ~50s (5x improvement)

---

## Security Considerations

**Credentials**:
- Never log passwords
- Store in environment variables only
- Use read-only account when possible

**Data Exposure**:
- PHI in booking `title` field (patient names)
- Log booking IDs, not patient identifiers
- Sanitize error messages (don't include `title` in logs)

**Network**:
- HTTPS required (TLS 1.2+)
- Certificate validation enabled
- Request timeout prevents hanging connections

---

## Testing

### Mock Responses

**For unit tests**, use fixtures in `tests/fixtures/calpendo_responses.json`:

```json
{
  "query_bookings_success": {
    "biskits": [
      {
        "id": 12345,
        "formattedName": "[2025-02-12 10:00:00.0, 2025-02-12 11:00:00.0]",
        "title": "SUB001 - John Doe",
        "status": "Approved",
        "biskitType": "MRIScan"
      }
    ]
  },
  "booking_detail_success": {
    "id": 12345,
    "properties": {
      "resource": {"formattedName": "3T Diagnostic"},
      "project": {"formattedName": "BRISKP (Study)"},
      "durationInMinutes": 60
    }
  },
  "error_401": {
    "error": "Unauthorized"
  }
}
```

### Integration Tests

**Test against real Calpendo API** (using test credentials):
- Create test booking via Calpendo UI
- Fetch via plugin
- Verify transformation
- Cancel booking
- Verify status update
- Delete via Calpendo UI
- Verify marked as DISCONTINUED in DB
