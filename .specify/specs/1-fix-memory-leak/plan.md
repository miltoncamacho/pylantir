# Implementation Plan: Fix Memory Leak in REDCap Synchronization

**Feature**: 1-fix-memory-leak
**Created**: 2025-11-26
**Status**: Active
**Priority**: Critical

---

## Executive Summary

**Problem**: Memory grows from 111MB to 713MB over 5 days (6.4x). Current cleanup frees 0 MB.

**Root Cause**: DataFrames, PyCap objects, and SQLAlchemy sessions not being released.

**Solution**: Minimal changes to `redcap_to_db.py` to explicitly clean up memory-holding references.

---

## Constitution Compliance Check

### I. Minimalist Dependencies ✅
- **Status**: COMPLIANT
- **No new dependencies required**
- Uses only existing core: pandas, SQLAlchemy, PyCap, gc (stdlib)
- Optional psutil already available for monitoring

### II. CLI-First Design ✅
- **Status**: COMPLIANT
- No CLI changes required
- All fixes internal to synchronization logic

### III. Healthcare Data Integrity ✅
- **Status**: COMPLIANT
- No changes to data transformations
- No changes to database transactions
- Memory cleanup happens AFTER successful sync

### IV. Test-Driven DICOM Integration ✅
- **Status**: COMPLIANT
- No changes to DICOM services
- Memory fixes isolated to REDCap sync module

### V. Operational Observability ✅
- **Status**: COMPLIANT
- Enhanced logging for memory cleanup effectiveness
- No changes to existing log levels or format

**GATE PASSED**: All constitution principles maintained. Proceed with implementation.

---

## Technical Context

### Current Architecture
```
fetch_redcap_entries()
  → Creates DataFrame from PyCap
  → Performs groupby operations (creates copies)
  → Returns list of dicts

sync_redcap_to_db()
  → Calls fetch_redcap_entries()
  → Creates SQLAlchemy session
  → Persists WorklistItem objects
  → Closes session
  → Calls cleanup_memory_and_connections()

cleanup_memory_and_connections()
  → Calls gc.collect() 3 times
  → Disposes engine pool
  → Returns (currently frees 0 MB)
```

### Memory Leak Sources

**Critical Issues** (must fix):
1. **DataFrame persistence**: DataFrame variable in `fetch_redcap_entries()` never deleted
2. **Groupby copies**: `groupby()` creates intermediate DataFrames that persist
3. **Session identity map**: SQLAlchemy keeps ORM objects after `session.close()`
4. **PyCap object**: `Project` instance retained in function scope

**Non-Critical** (skip for minimal fix):
- Connection pool tuning (pool already manages itself reasonably)
- Advanced memory profiling (psutil monitoring already exists)
- Logging optimization (not a primary leak source)

---

## Implementation Strategy

### Phase 1: Critical Fixes Only

**File**: `src/pylantir/redcap_to_db.py`

#### Change 1: Explicit DataFrame Cleanup in fetch_redcap_entries()

**Location**: After line ~66 (end of function)

**Change**:
```python
# Before returning, explicitly clean up DataFrame
del records
gc.collect()
return filtered_records
```

**Rationale**: DataFrame `records` holds entire REDCap export in memory. Must be deleted before function returns.

#### Change 2: Remove Groupby Intermediate References

**Location**: Lines ~70-90 (groupby loop)

**Change**:
```python
# Convert to list first to avoid holding groupby iterator
record_groups = list(records.groupby(level=0))

for record_id, group in record_groups:
    # Process as before...
    pass

# Clean up immediately after loop
del record_groups
del records
gc.collect()
```

**Rationale**: Groupby iterator holds reference to original DataFrame. Convert to list and delete both.

#### Change 3: SQLAlchemy Session Cleanup in sync_redcap_to_db()

**Location**: In finally block (line ~333)

**Change**:
```python
finally:
    if session:
        session.expunge_all()  # Detach all ORM objects
        session.close()

    cleanup_memory_and_connections()
```

**Rationale**: `expunge_all()` clears identity map, releasing ORM object references.

#### Change 4: PyCap Project Cleanup in fetch_redcap_entries()

**Location**: After data export (line ~56)

**Change**:
```python
records = project.export_records(...)

# Clean up project immediately after export
del project
gc.collect()

if records.empty:
    lgr.warning("No records retrieved from REDCap.")
    return []
```

**Rationale**: PyCap Project may cache API responses. Delete immediately after use.

#### Change 5: Enhanced Cleanup Logging

**Location**: In cleanup_memory_and_connections() (line ~146)

**Change**:
```python
def cleanup_memory_and_connections():
    """Cleanup memory and database connections."""
    memory_before = get_memory_usage()

    # Clear SQLAlchemy's internal caches
    if hasattr(engine, 'pool'):
        engine.pool.dispose()

    # Aggressive garbage collection targeting all generations
    collected = gc.collect(generation=2)  # Target oldest generation
    collected += gc.collect(generation=1)
    collected += gc.collect(generation=0)

    memory_after = get_memory_usage()

    if memory_before and memory_after and 'rss_mb' in memory_before:
        freed = memory_before['rss_mb'] - memory_after['rss_mb']
        lgr.info(
            f"Memory cleanup: Before={memory_before['rss_mb']:.1f}MB, "
            f"After={memory_after['rss_mb']:.1f}MB, "
            f"Freed={freed:.1f}MB, "
            f"Objects={collected}"
        )
    else:
        lgr.info(f"Memory cleanup: Collected {collected} objects")
```

**Rationale**: Target specific GC generations. Simplified logging shows essential metrics only.

---

## Testing Strategy

### Manual Validation

**Test 1: Short-term stability** (30 minutes)
```bash
# Start server, let run for 30 minutes
pylantir start --port 4242 --AEtitle MWL_SERVER --pylantir_config config.json

# Watch logs for cleanup effectiveness
tail -f logs/pylantir.log | grep "Memory cleanup"

# Expected: "Freed" > 0MB, "Objects" > 0
```

**Test 2: Memory monitoring script**
```bash
# Run existing test_memory_cleanup.py
python test_memory_cleanup.py

# Expected: No growth pattern over 10 cycles
```

**Test 3: Production simulation** (7 days)
```bash
# Deploy to test environment
# Monitor via system tools: htop, ps aux
# Expected: Memory stable < 150MB
```

### Success Metrics

**Critical** (must achieve):
- Memory freed > 0 MB per cleanup cycle
- Objects collected > 0 per cleanup cycle
- Memory growth < 5MB/day over 7 days

**Validation** (must pass):
- All existing tests pass (`pytest tests/`)
- No errors in 24-hour test run
- DICOM services remain responsive

---

## Risk Mitigation

### Risk 1: Aggressive cleanup breaks references
**Likelihood**: Low
**Mitigation**: Cleanup happens AFTER all processing, in finally block
**Rollback**: Git revert if issues detected

### Risk 2: Performance impact from multiple GC calls
**Likelihood**: Low
**Mitigation**: GC runs only after sync (every 30+ minutes), not in hot path
**Validation**: Measure sync time before/after (should be < 0.1s difference)

---

## Deployment Plan

### Pre-deployment
1. Create PR from `1-fix-memory-leak` branch
2. Run full test suite: `pytest tests/`
3. Run memory test: `python test_memory_cleanup.py`
4. Code review focusing on reference cleanup

### Deployment
1. Deploy to test environment first
2. Monitor for 24 hours
3. Check memory cleanup logs
4. If stable, deploy to production during maintenance window

### Post-deployment
1. Monitor memory via system tools for 7 days
2. Analyze cleanup logs daily
3. Document memory baseline and growth rate
4. If issues persist, escalate for deeper profiling

---

## Files to Modify

1. **src/pylantir/redcap_to_db.py**
   - `fetch_redcap_entries()`: Add explicit cleanup (5 changes)
   - `sync_redcap_to_db()`: Add expunge_all() (1 change)
   - `cleanup_memory_and_connections()`: Enhanced logging (1 change)
   - **Total**: ~15 lines added/modified

**No other files require changes.**

---

## Out of Scope

**Explicitly excluded** (per minimal requirements):
- Connection pool tuning (pool self-manages adequately)
- Memory profiling tools (psutil already available)
- Logging optimization (not a leak source)
- Memory monitoring dashboard (out of scope)
- Alternative database engines (separate decision)
- Advanced caching strategies (not needed)
- Thread-local cleanup (no threading in sync path)

---

## Success Criteria

**Implementation Complete When**:
1. All 5 code changes applied to `redcap_to_db.py`
2. Memory cleanup logs show: Freed > 0MB, Objects > 0
3. Full test suite passes
4. 24-hour test run shows stable memory

**Production Ready When**:
1. Test environment runs 7 days with < 150MB memory
2. Memory growth < 5MB/day
3. No DICOM service disruptions
4. Cleanup logs show consistent effectiveness

---

## Timeline Estimate

- **Implementation**: 2 hours (code changes + testing)
- **Testing**: 24 hours (automated test run)
- **Production validation**: 7 days (monitoring)

**Total**: Implementation complete in 1 day, full validation in 1 week.
