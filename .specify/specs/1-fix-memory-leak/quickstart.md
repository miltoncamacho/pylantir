# Quickstart: Implementing Memory Leak Fix

**Feature**: 1-fix-memory-leak
**Time to implement**: ~2 hours

---

## Quick Implementation Guide

### Step 1: Apply Code Changes (30 minutes)

Edit **src/pylantir/redcap_to_db.py** only. Five specific changes:

#### Change 1: Line ~40 - Delete PyCap Project after export
```python
# After: records = project.export_records(...)
# Add:
del project
gc.collect()
```

#### Change 2: Line ~70 - Convert groupby to list
```python
# Change from:
for record_id, group in records.groupby(level=0):

# To:
record_groups = list(records.groupby(level=0))
for record_id, group in record_groups:
```

#### Change 3: Line ~105 - Cleanup before return
```python
# Before: return filtered_records
# Add before return:
del record_groups
del records
gc.collect()
return filtered_records
```

#### Change 4: Line ~333 - Add expunge_all() in finally block
```python
# In finally block, before session.close():
if session:
    session.expunge_all()  # Add this line
    session.close()
```

#### Change 5: Line ~175 - Enhance cleanup logging
```python
# In cleanup_memory_and_connections(), replace logging with:
if memory_before and memory_after and 'rss_mb' in memory_before:
    freed = memory_before['rss_mb'] - memory_after['rss_mb']
    lgr.info(
        f"Memory cleanup: Before={memory_before['rss_mb']:.1f}MB, "
        f"After={memory_after['rss_mb']:.1f}MB, "
        f"Freed={freed:.1f}MB, "
        f"Objects={collected}"
    )
```

### Step 2: Test Changes (15 minutes)

```bash
# Run existing tests
pytest tests/

# Run memory cleanup test
python test_memory_cleanup.py

# Expected output:
# ✓ Tests pass
# ✓ Memory cleanup shows: Freed > 0MB, Objects > 0
```

### Step 3: Validate in Test Environment (24 hours)

```bash
# Start server
pylantir start --port 4242 --AEtitle MWL_SERVER --pylantir_config config.json

# Monitor logs (separate terminal)
tail -f logs/pylantir.log | grep "Memory cleanup"

# Expected log pattern every 30 minutes:
# Memory cleanup: Before=120.5MB, After=118.2MB, Freed=2.3MB, Objects=47
```

### Step 4: Monitor Memory (continuous)

```bash
# Watch process memory
watch -n 60 'ps aux | grep pylantir | grep -v grep'

# Expected:
# Memory stays < 150MB
# No continuous growth trend
```

---

## Expected Outcomes

### Before Fix
```
Memory cleanup completed. Before: 111.18MB, After: 111.19MB, Freed: -0.01MB, Collected 0 objects
[5 days later]
Memory cleanup completed. Before: 713.23MB, After: 713.23MB, Freed: 0.00MB, Collected 0 objects
```

### After Fix
```
Memory cleanup: Before=120.5MB, After=118.2MB, Freed=2.3MB, Objects=47
[5 days later]
Memory cleanup: Before=125.1MB, After=123.8MB, Freed=1.3MB, Objects=52
```

**Key metrics improved**:
- Freed: **-0.01MB → 2.3MB** (now freeing memory)
- Objects: **0 → 47** (now collecting objects)
- Growth: **600MB → ~5MB** over 5 days

---

## Troubleshooting

### Issue: Still seeing 0 MB freed

**Check**:
1. Verify all 5 changes applied correctly
2. Ensure `gc` imported at top of file
3. Check that `expunge_all()` is called BEFORE `close()`

**Debug**:
```python
# Add temporary debug logging
lgr.debug(f"Before del records: {sys.getsizeof(records)} bytes")
del records
gc.collect()
lgr.debug("After cleanup")
```

### Issue: Tests failing

**Most likely**: Import statement needed
```python
import gc  # Add if missing at top of redcap_to_db.py
```

### Issue: Performance degradation

**Check**: If sync takes > 5 seconds longer
- Profile with: `time python -c "from src.pylantir.redcap_to_db import sync_redcap_to_db; ..."`
- GC overhead should be < 0.5 seconds
- If higher, reduce gc.collect() calls to once after all deletions

---

## Rollback Plan

If issues detected:
```bash
git revert <commit-hash>
git push
# Restart server
```

Memory will return to leaking state but system remains functional.

---

## Success Checklist

- [ ] All 5 code changes applied
- [ ] `pytest tests/` passes
- [ ] Memory cleanup logs show Freed > 0MB
- [ ] Memory cleanup logs show Objects > 0
- [ ] 24-hour test shows stable memory
- [ ] No DICOM service disruptions

When all checked: **Ready for production deployment**
