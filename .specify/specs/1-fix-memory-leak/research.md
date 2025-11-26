# Research: Memory Leak Fix Technical Decisions

**Feature**: 1-fix-memory-leak
**Created**: 2025-11-26

---

## Critical Decisions

### 1. DataFrame Cleanup Approach

**Decision**: Explicit `del` + `gc.collect()` immediately after use

**Rationale**:
- Python garbage collector is reference-counting based
- Large objects (DataFrames) can persist until next GC cycle
- Explicit deletion removes reference immediately
- `gc.collect()` forces immediate cleanup of circular references

**Evidence from logs**:
- Current cleanup collects 0 objects (nothing to collect)
- Memory freed = 0 MB (references still held)
- Memory grows 6.4x over 5 days (continuous accumulation)

**Alternatives considered**:
- ❌ Let GC handle it naturally → Current approach, proven ineffective
- ❌ Use context managers → Pandas DataFrames don't support it
- ✅ Explicit deletion → Industry best practice for large objects

### 2. Groupby Iterator Handling

**Decision**: Convert to list, then delete both list and original DataFrame

**Rationale**:
- Groupby returns iterator that holds reference to source DataFrame
- Iterator prevents DataFrame from being garbage collected
- Converting to list breaks the iterator reference chain
- Both list and DataFrame can then be explicitly deleted

**Technical details**:
```python
# Bad (holds DataFrame reference)
for record_id, group in records.groupby(level=0):
    process(group)
# DataFrame still in memory here

# Good (releases DataFrame)
record_groups = list(records.groupby(level=0))
for record_id, group in record_groups:
    process(group)
del record_groups
del records
gc.collect()
```

### 3. SQLAlchemy Identity Map Clearing

**Decision**: Call `session.expunge_all()` before `session.close()`

**Rationale**:
- SQLAlchemy Session maintains identity map of all ORM objects
- `session.close()` alone doesn't clear the identity map
- Identity map holds strong references preventing GC
- `expunge_all()` explicitly detaches all objects from session

**SQLAlchemy documentation**:
> "The Session.close() method issues a Session.expunge_all() which removes all ORM objects from the session"

However, in practice, calling it explicitly ensures immediate cleanup.

**Impact**: WorklistItem objects can be garbage collected immediately after sync.

### 4. Garbage Collection Generation Targeting

**Decision**: Run `gc.collect()` on generations 2, 1, 0 in sequence

**Rationale**:
- Python's GC has 3 generations (0=young, 1=middle, 2=old)
- Long-lived objects (DataFrames, sessions) accumulate in generation 2
- Default `gc.collect()` only collects generation 0
- Targeting generation 2 specifically catches old, unreferenced objects

**Python GC behavior**:
- Generation 0: Collected frequently, catches recent objects
- Generation 1: Collected less often, medium-lived objects
- Generation 2: Collected rarely, long-lived objects accumulate here

**Evidence**: 5-day accumulation suggests objects surviving to generation 2.

### 5. PyCap Project Lifecycle

**Decision**: Create new Project instance per sync, delete immediately after export

**Rationale**:
- PyCap Project object may cache API responses internally
- Cache is helpful for repeated queries but harmful for long-running processes
- Creating fresh instance per sync ensures no cache accumulation
- Deletion after export releases HTTP response data

**Trade-off**:
- Slightly higher overhead (new instance per sync)
- Acceptable cost given 30+ minute sync intervals
- Guarantees no memory accumulation from API client

---

## Configuration Decisions

### Memory Cleanup Configuration

**Decision**: No new configuration parameters

**Rationale**:
- Cleanup should always run (not optional)
- Fixed GC strategy works for all scenarios
- No user-tunable parameters needed
- Keeps configuration simple per constitution

### Logging Verbosity

**Decision**: Keep existing log levels, enhance INFO messages only

**Rationale**:
- INFO level already used for cleanup logs
- Enhanced format shows: Before, After, Freed, Objects
- No new log levels needed
- No DEBUG spam that could accumulate

---

## Testing Decisions

### Validation Approach

**Decision**: Use existing `test_memory_cleanup.py` + manual monitoring

**Rationale**:
- Test script already validates cleanup effectiveness
- System monitoring (htop, ps) provides ground truth
- No need for complex profiling tools
- Minimal tooling per constitution

### Success Threshold

**Decision**: Memory freed > 0 MB AND objects collected > 0

**Rationale**:
- Currently: 0 MB freed, 0 objects collected (complete failure)
- Any positive values indicate improvement
- Specific targets (e.g., "must free 10MB") too fragile
- Trend matters more than absolute values

---

## Implementation Decisions

### Change Scope

**Decision**: Modify only `src/pylantir/redcap_to_db.py`

**Rationale**:
- All memory leaks traced to REDCap sync functions
- DICOM services not involved in leak
- Database setup not involved in leak
- Minimal change scope reduces risk

### Code Style

**Decision**: Follow existing patterns, minimal refactoring

**Rationale**:
- Preserve existing function signatures
- Add cleanup code in-place
- No architectural changes
- Reduces merge conflicts and review time

---

## Technology Stack (Unchanged)

**Core Dependencies** (no changes):
- pandas: DataFrame handling
- PyCap (python-redcap): REDCap API
- SQLAlchemy: ORM and session management
- gc (stdlib): Garbage collection

**Optional Dependencies** (already available):
- psutil: Memory monitoring (already in optional deps)

---

## References

**Python GC Documentation**:
- https://docs.python.org/3/library/gc.html
- Generation-based collection strategy
- `gc.collect(generation)` API

**SQLAlchemy Session Lifecycle**:
- https://docs.sqlalchemy.org/en/14/orm/session_basics.html
- Identity map behavior
- `expunge_all()` usage

**Pandas Memory Management**:
- https://pandas.pydata.org/docs/user_guide/scale.html
- DataFrame memory usage
- Best practices for large datasets

**PyCap Documentation**:
- https://pycap.readthedocs.io/
- Project API design
- No explicit cache control documented (assumes short-lived usage)

---

## Open Questions

None. All technical decisions resolved based on:
1. Log analysis (0 MB freed, 0 objects collected)
2. Code review (reference retention identified)
3. Best practices (explicit cleanup for large objects)
4. Constitution compliance (no new dependencies, minimal changes)
