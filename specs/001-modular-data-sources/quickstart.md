# Quick Start: Migrating to Modular Data Sources

**Feature**: 001-modular-data-sources
**Audience**: Pylantir administrators
**Time to Complete**: 5-10 minutes

---

## Overview

Pylantir now supports a modular data source architecture that allows you to configure multiple data sources for populating the DICOM worklist. This guide helps you migrate from the legacy REDCap-only configuration to the new flexible format.

**Key Benefits**:
- ✅ Configure multiple data sources simultaneously
- ✅ Per-source sync intervals and operation windows
- ✅ Better audit trails with source tracking
- ✅ Easier to add custom data sources in the future

**Backward Compatibility**: Your existing configuration will continue working without changes, but we recommend migrating to benefit from new features.

---

## For Existing REDCap Users

### Current Configuration (Still Supported)

If you have a configuration file like this:

```json
{
  "db_path": "~/Desktop/worklist.db",
  "db_echo": "False",
  "db_update_interval": 60,
  "operation_interval": {
    "start_time": [8, 0],
    "end_time": [18, 0]
  },
  "allowed_aet": ["MRI_SCANNER"],
  "site": "792",
  "protocol": {
    "792": "BRAIN_MRI_3T",
    "mapping": "GEHC"
  },
  "redcap2wl": {
    "study_id": "study_id",
    "mri_instance": "session_id",
    "family_id": "family_id",
    "youth_dob_y": "patient_birth_date",
    "demo_sex": "patient_sex",
    "mri_date": "scheduled_start_date",
    "mri_time": "scheduled_start_time"
  }
}
```

**Good news**: This will continue working! Pylantir will auto-convert it to the new format internally and log a warning message.

---

### New Configuration (Recommended)

Here's the same configuration in the new format:

```json
{
  "db_path": "~/Desktop/worklist.db",
  "db_echo": "False",
  "allowed_aet": ["MRI_SCANNER"],

  "data_sources": [
    {
      "name": "main_redcap",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 60,
      "operation_interval": {
        "start_time": [8, 0],
        "end_time": [18, 0]
      },
      "config": {
        "site_id": "792",
        "protocol": {
          "792": "BRAIN_MRI_3T",
          "mapping": "GEHC"
        }
      },
      "field_mapping": {
        "study_id": "study_id",
        "mri_instance": "session_id",
        "family_id": "family_id",
        "youth_dob_y": "patient_birth_date",
        "demo_sex": "patient_sex",
        "mri_date": "scheduled_start_date",
        "mri_time": "scheduled_start_time"
      }
    }
  ]
}
```

**What Changed**:
1. ✅ Moved `db_update_interval` → `data_sources[0].sync_interval`
2. ✅ Moved `operation_interval` → `data_sources[0].operation_interval`
3. ✅ Moved `site` and `protocol` → `data_sources[0].config`
4. ✅ Moved `redcap2wl` → `data_sources[0].field_mapping`
5. ✅ Added `name` (you choose), `type` ("redcap"), and `enabled` (true)

---

## Migration Steps

### Step 1: Backup Current Configuration

Always backup before making changes:

```bash
cp ~/Desktop/mwl_config.json ~/Desktop/mwl_config.json.backup
```

### Step 2: Update Configuration File

Open your configuration file and restructure it using the example above:

```bash
# Edit your config file
nano ~/Desktop/mwl_config.json  # or use your preferred editor
```

**Configuration Template**:

```json
{
  "db_path": "~/Desktop/worklist.db",
  "db_echo": "False",
  "allowed_aet": ["MRI_SCANNER"],

  "data_sources": [
    {
      "name": "YOUR_SOURCE_NAME",         // Choose a descriptive name
      "type": "redcap",                    // Must be "redcap" for now
      "enabled": true,                     // Set to false to disable this source
      "sync_interval": 60,                 // Seconds between syncs
      "operation_interval": {
        "start_time": [8, 0],             // Start syncing at 8:00 AM
        "end_time": [18, 0]               // Stop syncing at 6:00 PM
      },
      "config": {
        "site_id": "YOUR_SITE_ID",
        "protocol": {
          "YOUR_SITE_ID": "YOUR_PROTOCOL"
        }
      },
      "field_mapping": {
        // Map your REDCap fields to worklist fields
        "study_id": "study_id",
        "mri_instance": "session_id",
        "youth_dob_y": "patient_birth_date",
        "demo_sex": "patient_sex",
        "mri_date": "scheduled_start_date",
        "mri_time": "scheduled_start_time"
      }
    }
  ]
}
```

### Step 3: Validate Configuration

Start Pylantir and watch for validation errors:

```bash
pylantir start --pylantir-config ~/Desktop/mwl_config.json
```

**Look for these log messages**:
- ✅ **Success**: `Data source 'YOUR_SOURCE_NAME' validated successfully`
- ⚠️ **Warning**: `Legacy configuration detected. Consider migrating to 'data_sources' format.` (if you didn't migrate yet)
- ❌ **Error**: `Data source 'YOUR_SOURCE_NAME' configuration invalid: ...` (fix the error and restart)

### Step 4: Verify Database Population

Query the database to ensure entries are being synced:

```bash
# In another terminal
pylantir query-db
```

You should see worklist entries with the new `data_source` field populated:

```
Patient ID: sub_12345_ses_1_fam_99_site_792
Patient Name: cpip-id-12345^fa-99
Source: main_redcap  ← New field!
Scheduled Date: 20260126
```

### Step 5: Remove Backup (Optional)

Once you've verified everything works, you can remove the backup:

```bash
rm ~/Desktop/mwl_config.json.backup
```

---

## Environment Variables

**No changes required**. The REDCap plugin still uses the same environment variables:

```bash
# In your .env file or shell environment
export REDCAP_API_URL="https://redcap.institution.edu/api/"
export REDCAP_API_TOKEN="your_secure_token_here"
```

---

## Configuration Reference

### Data Source Object

Each object in the `data_sources` array has these fields:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | String | Yes | N/A | Unique identifier for this source (used in logs and database) |
| `type` | String | Yes | N/A | Plugin type ("redcap" for now, more in future) |
| `enabled` | Boolean | No | `true` | Set to `false` to temporarily disable this source |
| `sync_interval` | Number | No | `60` | Seconds between syncs (minimum: 1) |
| `operation_interval.start_time` | Array[2] | No | `[0, 0]` | Start syncing at this time [hour, minute] |
| `operation_interval.end_time` | Array[2] | No | `[23, 59]` | Stop syncing at this time [hour, minute] |
| `config` | Object | Yes | N/A | Plugin-specific configuration (see below) |
| `field_mapping` | Object | Yes | N/A | Maps source fields to worklist fields (see below) |

### REDCap Plugin Configuration

The `config` object for REDCap sources:

```json
{
  "config": {
    "site_id": "792",              // Your site identifier
    "protocol": {
      "792": "BRAIN_MRI_3T",       // Protocol name for this site
      "mapping": "GEHC"            // Optional: Equipment mapping
    }
  }
}
```

### Field Mapping

The `field_mapping` object maps REDCap fields to DICOM worklist fields:

**Required Mappings**:
```json
{
  "field_mapping": {
    "study_id": "study_id",                      // Study ID (used in patient_id)
    "mri_instance": "session_id",                 // Session/visit ID
    "family_id": "family_id",                     // Family ID (used in patient_name)
    "youth_dob_y": "patient_birth_date",          // Birth date (YYYYMMDD)
    "demo_sex": "patient_sex",                    // Sex (M/F/O)
    "mri_date": "scheduled_start_date",           // Exam date (YYYYMMDD)
    "mri_time": "scheduled_start_time"            // Exam time (HHMMSS)
  }
}
```

**How it works**: Left side is your REDCap field name, right side is the internal worklist field name (don't change these).

---

## Troubleshooting

### Error: "Missing required configuration key"

**Symptom**:
```
Data source 'main_redcap' configuration invalid: Missing required key: site_id
```

**Solution**: Add the missing key to the `config` object:
```json
"config": {
  "site_id": "YOUR_SITE_ID",  // ← Add this
  "protocol": {...}
}
```

### Error: "Unknown data source type"

**Symptom**:
```
Unknown data source type: 'redcapp'. Available: ['redcap']
```

**Solution**: Fix the typo in `type` field:
```json
"type": "redcap"  // ← Correct spelling
```

### Warning: "Legacy configuration detected"

**Symptom**:
```
Legacy configuration detected. Consider migrating to 'data_sources' format.
```

**Solution**: This is just a warning. Your config still works, but consider migrating using this guide for future benefits.

### Error: "Duplicate data source name"

**Symptom**:
```
Duplicate data source name: 'main_redcap'
```

**Solution**: Each source must have a unique `name`:
```json
"data_sources": [
  {"name": "site_a_redcap", ...},
  {"name": "site_b_redcap", ...}  // ← Different name
]
```

### Sync Not Working

**Check these**:
1. ✅ Environment variables set (`REDCAP_API_URL`, `REDCAP_API_TOKEN`)
2. ✅ `enabled` is `true` (not `false`)
3. ✅ Current time is within `operation_interval`
4. ✅ REDCap API is accessible (test with `curl`)
5. ✅ Field mappings are correct (check REDCap field names)

**Enable debug logging**:
```bash
export DEBUG=True
pylantir start --pylantir-config ~/Desktop/mwl_config.json
```

---

## Advanced: Multiple Sources (Future)

**Note**: This is a preview of future capabilities. Only REDCap is supported in Phase 1.

Once additional plugins are available, you can configure multiple sources:

```json
{
  "data_sources": [
    {
      "name": "site_a_redcap",
      "type": "redcap",
      "sync_interval": 60,
      "config": {...},
      "field_mapping": {...}
    },
    {
      "name": "site_b_csv",
      "type": "csv",
      "sync_interval": 300,
      "config": {
        "file_path": "/data/worklist/site_b.csv"
      },
      "field_mapping": {...}
    }
  ]
}
```

Each source will sync independently to the same database.

---

## Next Steps

1. ✅ **Test your configuration** with `pylantir start`
2. ✅ **Verify data syncing** with `pylantir query-db`
3. ✅ **Monitor logs** for any issues
4. 📚 **Read the full documentation** in `/specs/001-modular-data-sources/plan.md`
5. 🔮 **Stay tuned** for additional data source plugins (CSV, JSON, custom)

---

## Support

**Questions or issues?** Check:
- [Feature Specification](spec.md) - Detailed requirements
- [Implementation Plan](plan.md) - Technical details
- [Data Model](data-model.md) - Configuration schema reference

**Found a bug?** Report it with:
- Your configuration file (redact sensitive tokens!)
- Error messages from logs
- Pylantir version (`pylantir --version`)
- Steps to reproduce
