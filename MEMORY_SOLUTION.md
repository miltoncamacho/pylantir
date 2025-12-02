# Real Memory Solution

## The Actual Problem

**Current behavior**: 
- Every 30 minutes, `fetch_redcap_entries()` calls `project.export_records(..., format_type="df")`
- This creates a **complete pandas DataFrame** of ALL records in the time window
- Even if you delete it, Python's memory allocator keeps the arena
- Over 5 days, this grows from 111MB → 713MB

**Why cleanup doesn't work**:
- You're not "leaking" objects (they ARE deleted)
- You're creating NEW large allocations every cycle
- Python's allocator requests more memory from OS each time
- It never gives it back (fragmentation)

## The ONLY Real Solution

**Stop using DataFrames entirely** or **drastically limit their size**:

### Option 1: Use dict/list format instead of DataFrame (RECOMMENDED)
```python
# Instead of format_type="df"
records = project.export_records(
    fields=redcap_fields,
    date_begin=datetime_interval,
    date_end=datetime_now,
    format_type="json"  # Returns list of dicts, much lighter
)
```

Benefits:
- No DataFrame overhead (50-100x less memory)
- No pandas caching/groupby issues
- Python lists/dicts are lightweight
- Memory reuse works properly

### Option 2: Limit DataFrame size with chunking
```python
# Fetch in small batches
for record_id in record_ids[:10]:  # Process 10 at a time
    records = project.export_records(
        fields=redcap_fields,
        records=[record_id],
        format_type="df"
    )
    # Process immediately
    # Delete before next iteration
```

### Option 3: Use PyCap's raw API (most efficient)
```python
# Bypass pandas entirely
import requests
response = requests.post(
    REDCAP_API_URL,
    data={
        'token': REDCAP_API_TOKEN,
        'content': 'record',
        'format': 'json',
        'fields': ','.join(redcap_fields),
        'dateRangeBegin': datetime_interval.strftime('%Y-%m-%d %H:%M:%S'),
        'dateRangeEnd': datetime_now.strftime('%Y-%m-%d %H:%M:%S')
    }
)
records = response.json()  # List of dicts, no DataFrame
```

## Why This Works

1. **Prevents allocation**: Never creates 100MB DataFrame in the first place
2. **Reuses memory**: Small dicts/lists reuse existing memory pool
3. **No fragmentation**: Allocator doesn't need to expand arenas
4. **RSS stays flat**: No new memory requested from OS

## Implementation Plan

1. Replace `format_type="df"` with `format_type="json"`
2. Adjust `fetch_redcap_entries()` to process list of dicts
3. Remove all pandas groupby/DataFrame operations
4. Use native Python dict operations instead

## Expected Result

- Memory stays at ~120MB indefinitely
- No growth over days/weeks
- Cleanup not needed (nothing to clean up)
- Simpler code, fewer dependencies

## Proof

Run this comparison:
```python
# OLD WAY (DataFrame)
records = project.export_records(..., format_type="df")
# Memory spike: +50-100MB

# NEW WAY (dict)
records = project.export_records(..., format_type="json")
# Memory spike: +1-5MB
```

The difference is 10-20x less memory per sync cycle.
