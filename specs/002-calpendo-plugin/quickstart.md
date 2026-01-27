# Quickstart: Calpendo Data Source Plugin

**Feature**: 002-calpendo-plugin  
**Purpose**: Get started with the Calpendo plugin in 5 minutes  
**Audience**: System administrators configuring Pylantir

---

## Prerequisites

- Pylantir installed and working
- Calpendo server access (URL + credentials)
- Python 3.8+ with `requests` and `pytz` libraries

**Install Dependencies**:
```bash
pip install requests pytz
```

---

## Step 1: Configure Environment Variables

Set Calpendo API credentials in your environment:

```bash
# Calpendo server URL
export CALPENDO_API_URL="https://sfc-calgary.calpendo.com"

# Read-only account credentials
export CALPENDO_USERNAME="your_username"
export CALPENDO_PASSWORD="your_password"
```

**Security Note**: Never commit credentials to version control. Use `.env` file or system environment.

---

## Step 2: Configure Data Source

Add Calpendo data source to your Pylantir configuration file (e.g., `mwl_config.json`):

### Minimal Configuration

```json
{
  "data_sources": [
    {
      "name": "calpendo_3t",
      "type": "calpendo",
      "enabled": true,
      "sync_interval": 300,
      "config": {
        "resources": ["3T Diagnostic"]
      },
      "field_mapping": {
        "title": {
          "_extract": {
            "patient_id": {"pattern": "^([A-Z0-9]+)", "group": 1},
            "patient_name": {"pattern": " - (.+)$", "group": 1}
          }
        },
        "project.formattedName": {
          "_extract": {
            "study_description": {"pattern": "^([^(]+)", "group": 1}
          }
        },
        "resource.formattedName": "modality",
        "status": "performed_procedure_step_status"
      }
    }
  ]
}
```

**Explanation**:
- `name`: Unique identifier for this data source
- `type`: `"calpendo"` (plugin type)
- `enabled`: `true` to activate syncing
- `sync_interval`: 300 seconds (5 minutes between syncs)
- `config.resources`: List of scanner names to fetch bookings for
- `field_mapping`: How to extract worklist fields from Calpendo bookings

---

### Full Configuration (All Options)

```json
{
  "data_sources": [
    {
      "name": "calpendo_3t",
      "type": "calpendo",
      "enabled": true,
      "sync_interval": 300,
      "operation_interval": {
        "start_time": [6, 0],
        "end_time": [20, 0]
      },
      "config": {
        "base_url": "https://sfc-calgary.calpendo.com",
        "resources": ["3T Diagnostic", "Mock Scanner"],
        "status_filter": "Approved",
        "lookback_multiplier": 2,
        "timezone": "America/Edmonton",
        "resource_modality_mapping": {
          "3T": "MR",
          "Mock": "OT"
        }
      },
      "field_mapping": {
        "title": {
          "_extract": {
            "patient_id": {"pattern": "^([A-Z0-9]+)", "group": 1},
            "patient_name": {"pattern": " - (.+)$", "group": 1}
          }
        },
        "project.formattedName": {
          "_extract": {
            "study_description": {"pattern": "^([^(]+)", "group": 1}
          }
        },
        "formattedName": {
          "_extract": {
            "scheduled_start_date": {"pattern": "^\\[([0-9-]+)", "group": 1},
            "scheduled_start_time": {"pattern": "([0-9:]+\\.[0-9])", "group": 1}
          }
        },
        "resource.formattedName": "modality",
        "status": "performed_procedure_step_status",
        "durationInMinutes": "scheduled_procedure_step_duration"
      }
    }
  ]
}
```

**Additional Options**:
- `operation_interval`: Only sync between 6:00 AM and 8:00 PM
- `config.base_url`: Override environment variable (optional)
- `config.status_filter`: Only sync bookings with this status (e.g., "Approved")
- `config.lookback_multiplier`: How far back to look (default: 2x sync_interval)
- `config.timezone`: Timezone for timestamp parsing (default: "America/Edmonton")
- `config.resource_modality_mapping`: Map resource names to DICOM modalities

---

## Step 3: Start Pylantir

Run Pylantir with your configuration:

```bash
pylantir start --pylantir_config /path/to/mwl_config.json
```

**Expected Output**:
```
INFO Using new data_sources configuration format
INFO [calpendo:calpendo_3t] Calpendo plugin validated for resources: ['3T Diagnostic']
INFO [calpendo:calpendo_3t] Starting sync loop (interval: 300s)
INFO [calpendo:calpendo_3t] Fetching bookings from 2026-01-27 08:30 to 2026-01-28 10:30
INFO [calpendo:calpendo_3t] Retrieved 5 bookings from Calpendo
INFO [calpendo:calpendo_3t] New booking 12345: SUB001
INFO [calpendo:calpendo_3t] Fetched 5 worklist entries from Calpendo
```

---

## Step 4: Verify Worklist

Query the worklist database to confirm bookings are synced:

```bash
pylantir query-db
```

**Expected Output**:
```
Study UID: 1.2.840.113619.2.55.3.12345...
Patient ID: SUB001
Patient Name: Doe^John
Modality: MR
Start Date: 2025-02-12
Start Time: 17:00:00
Status: SCHEDULED
Data Source: calpendo_3t
```

---

## Configuration Examples

### Multiple Resources (3T + EEG)

```json
{
  "config": {
    "resources": ["3T Diagnostic", "EEG"]
  }
}
```

### Different Title Formats

**Format 1**: `"SUB001 - John Doe"`
```json
{
  "title": {
    "_extract": {
      "patient_id": {"pattern": "^([A-Z0-9]+)", "group": 1},
      "patient_name": {"pattern": " - (.+)$", "group": 1}
    }
  }
}
```

**Format 2**: `"John Doe (SUB001)"`
```json
{
  "title": {
    "_extract": {
      "patient_name": {"pattern": "^([^(]+)", "group": 1},
      "patient_id": {"pattern": "\\(([A-Z0-9]+)\\)", "group": 1}
    }
  }
}
```

**Format 3**: `"SUB001"` (ID only)
```json
{
  "title": {
    "_extract": {
      "patient_id": {"pattern": "^(.+)$", "group": 1}
    }
  }
}
```
(patient_name will use fallback = patient_id)

### Filter by Status

Only sync approved bookings:
```json
{
  "config": {
    "status_filter": "Approved"
  }
}
```

### Adjust Sync Window

Look back 10 minutes (5-minute interval × 2 multiplier):
```json
{
  "sync_interval": 300,
  "config": {
    "lookback_multiplier": 2
  }
}
```

Look back 30 minutes (5-minute interval × 6 multiplier):
```json
{
  "sync_interval": 300,
  "config": {
    "lookback_multiplier": 6
  }
}
```

---

## Troubleshooting

### Authentication Errors

**Error**: `PluginConfigError: Invalid Calpendo credentials (401 Unauthorized)`

**Solution**:
1. Verify environment variables are set: `echo $CALPENDO_USERNAME`
2. Test credentials manually:
   ```bash
   curl -u "$CALPENDO_USERNAME:$CALPENDO_PASSWORD" "$CALPENDO_API_URL/webdav/q/Calpendo.Booking/..."
   ```
3. Check for special characters in password (may need escaping)

---

### No Bookings Fetched

**Error**: `INFO Retrieved 0 bookings from Calpendo`

**Possible Causes**:
1. **No bookings in time window**: Increase `lookback_multiplier` or check Calpendo directly
2. **Wrong resource names**: Check exact resource names in Calpendo (case-sensitive, spaces matter)
3. **Status filter too restrictive**: Remove `status_filter` or change to `null`

**Debug Steps**:
```bash
# Check what resources exist in Calpendo
curl -u "$CALPENDO_USERNAME:$CALPENDO_PASSWORD" \
  "$CALPENDO_API_URL/webdav/q/Calpendo.Resource"

# Manually query bookings for today
curl -u "$CALPENDO_USERNAME:$CALPENDO_PASSWORD" \
  "$CALPENDO_API_URL/webdav/q/Calpendo.Booking/AND/dateRange.start/GE/20260127-0000/dateRange.start/LT/20260128-0000"
```

---

### Regex Extraction Failures

**Error**: `WARNING Pattern '^([A-Z0-9]+)' failed on 'John Doe' for field 'patient_id'`

**Solution**:
1. Check actual `title` format in Calpendo
2. Adjust regex pattern to match:
   ```json
   {
     "pattern": "^([A-Z0-9]+)",  // Matches: "SUB001 - John"
     "pattern": "\\(([A-Z0-9]+)\\)",  // Matches: "John (SUB001)"
     "pattern": "^(.+)$"  // Matches: anything (fallback)
   }
   ```
3. Test regex online: https://regex101.com/ (select Python flavor)

---

### Timezone Issues

**Error**: Worklist times don't match Calpendo times

**Cause**: Calpendo returns Mountain Time, Pylantir stores UTC

**Verification**:
1. Check booking in Calpendo: `2025-02-12 10:00 AM MST`
2. Check worklist DB: `2025-02-12 17:00:00` (UTC = MST + 7 hours)
3. This is **correct** - DICOM worklist uses UTC internally

**If times are still wrong**:
- Verify `timezone` config: `"timezone": "America/Edmonton"`
- Check DST transitions (spring forward / fall back dates)
- Ensure `pytz` is installed and up-to-date

---

### Performance Issues

**Issue**: Sync takes too long (>30 seconds)

**Solutions**:
1. **Reduce lookback window**:
   ```json
   {"lookback_multiplier": 1}  // Instead of 2
   ```

2. **Filter by status**:
   ```json
   {"status_filter": "Approved"}  // Skip pending bookings
   ```

3. **Check API latency**:
   ```bash
   time curl -u "$CALPENDO_USERNAME:$CALPENDO_PASSWORD" "$CALPENDO_API_URL/webdav/q/Calpendo.Booking/..."
   ```

4. **Verify parallel fetching** (check logs for concurrent requests)

---

## Advanced Configuration

### Multiple Calpendo Sources

Sync different resources to separate data sources (for different modalities):

```json
{
  "data_sources": [
    {
      "name": "calpendo_3t_mri",
      "type": "calpendo",
      "enabled": true,
      "sync_interval": 300,
      "config": {
        "resources": ["3T Diagnostic"]
      },
      "field_mapping": { /* MRI-specific mapping */ }
    },
    {
      "name": "calpendo_eeg",
      "type": "calpendo",
      "enabled": true,
      "sync_interval": 600,
      "config": {
        "resources": ["EEG"]
      },
      "field_mapping": { /* EEG-specific mapping */ }
    }
  ]
}
```

**Benefits**:
- Different sync intervals per modality
- Different field extraction patterns
- Separate data_source tags in worklist

---

### Custom Modality Mapping

Map Calpendo resources to DICOM modalities:

```json
{
  "config": {
    "resource_modality_mapping": {
      "3T": "MR",
      "7T": "MR",
      "EEG": "EEG",
      "Mock": "OT",
      "PET": "PT"
    }
  }
}
```

**Fallback**: If resource doesn't match any prefix, uses `"OT"` (Other)

---

### Regex Pattern Library

**Common Patterns**:

| Pattern | Matches | Example |
|---------|---------|---------|
| `^([A-Z0-9]+)` | Start of string, alphanumeric | `"SUB001 - John"` → `"SUB001"` |
| ` - (.+)$` | Everything after " - " | `"SUB001 - John Doe"` → `"John Doe"` |
| `\\(([^)]+)\\)` | Content in parentheses | `"John (SUB001)"` → `"SUB001"` |
| `^([^(]+)` | Everything before "(" | `"BRISKP (Study)"` → `"BRISKP "` |
| `([0-9-]+)` | Dates (YYYY-MM-DD) | `"[2025-02-12 10:00"` → `"2025-02-12"` |
| `([0-9:]+\\.[0-9])` | Times (HH:MM:SS.f) | `"10:00:00.0, 11:00"` → `"10:00:00.0"` |

**Testing Patterns**:
```python
import re
test_string = "SUB001 - John Doe"
pattern = "^([A-Z0-9]+)"
match = re.search(pattern, test_string)
print(match.group(1))  # Output: SUB001
```

---

## Next Steps

1. **Monitor Logs**: Watch for warnings/errors during sync cycles
2. **Validate Data**: Query worklist DB and compare with Calpendo UI
3. **Tune Sync Interval**: Adjust based on booking creation patterns
4. **Test Cancellations**: Cancel a booking in Calpendo, verify it's marked DISCONTINUED
5. **Performance Tuning**: Monitor sync duration, adjust `lookback_multiplier` if needed

**Documentation**:
- API Reference: [contracts/calpendo-api.md](contracts/calpendo-api.md)
- Data Model: [data-model.md](data-model.md)
- Implementation Plan: [plan.md](plan.md)

**Support**:
- Check logs: Pylantir logs all API requests and responses at DEBUG level
- Enable debug logging: `export DEBUG=1` before starting Pylantir
- Report issues: Include booking ID, Calpendo resource, and error message
