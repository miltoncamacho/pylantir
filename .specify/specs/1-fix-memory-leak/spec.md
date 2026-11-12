# Feature Specification: Fix Persistent Memory Leak in REDCap Synchronization

**Feature ID**: 1
**Feature Name**: fix-memory-leak
**Created**: 2025-11-26
**Status**: Draft
**Priority**: Critical

## Overview

The Pylantir MWL server experiences severe memory leaks during long-running operations, with memory usage growing from 111MB to 713MB over 5 days (6.4x increase). The current cleanup mechanisms are ineffective, freeing virtually 0 MB despite garbage collection attempts. This memory leak threatens production stability and could lead to system crashes in healthcare environments where continuous uptime is critical.

## Problem Statement

**Current Behavior:**
- Memory grows from 111MB (Nov 21) to 713MB (Nov 26) over 5 days
- Memory cleanup reports: "Freed: 0.00MB, Collected 0 objects"
- Garbage collection attempts are ineffective
- Memory continues accumulating with each REDCap synchronization cycle
- System eventually becomes unstable and requires restart

**Impact:**
- **Critical**: Server crashes during clinical imaging procedures could cause patient safety issues
- **Operational**: Requires manual server restarts, disrupting imaging workflows
- **Resource**: Excessive memory consumption affects server performance
- **Reliability**: Violates healthcare uptime requirements (99.9% availability)

**Root Causes Identified:**
1. **DataFrame Accumulation**: Pandas DataFrames from `project.export_records()` are not explicitly deleted
2. **Groupby Memory Retention**: `groupby()` operations create DataFrame copies that persist in memory
3. **SQLAlchemy Session Leaks**: ORM objects remain referenced after session close
4. **Connection Pool Growth**: Database connection pool may be growing unbounded
5. **REDCap API Client Caching**: PyCap Project objects may cache responses internally
6. **Logging References**: Log messages containing large data structures may prevent garbage collection

## User Scenarios & Testing

### Scenario 1: Long-Running Production Server
**Actor**: System Administrator
**Context**: Pylantir MWL server running continuously for clinical imaging operations
**Flow**:
1. Server starts with baseline memory usage (~100-120MB)
2. Server runs for 5+ days with regular REDCap synchronization (every 30 minutes)
3. Administrator monitors server memory usage via system tools
4. Memory usage remains stable within acceptable range (< 150MB)
5. No manual intervention or restarts required

**Success Criteria**:
- Memory usage stabilizes at < 150MB after initial ramp-up
- No memory growth > 5MB per day during steady-state operation
- Server runs continuously for 7+ days without requiring restart
- Memory cleanup logs show effective garbage collection (> 0MB freed per cycle)

### Scenario 2: High-Frequency Synchronization
**Actor**: REDCap Integration System
**Context**: Hospital environment with frequent patient updates requiring 5-minute sync intervals
**Flow**:
1. Server configured for high-frequency sync (every 5 minutes)
2. System processes 100+ REDCap records per sync cycle
3. Server runs through 288 sync cycles per day
4. Memory usage remains controlled despite high operation frequency
5. Performance metrics show consistent response times

**Success Criteria**:
- Memory growth < 10MB per 1000 sync cycles
- Sync performance remains stable (< 5 seconds per cycle)
- No memory-related warnings in logs
- Garbage collection successfully frees memory between cycles

### Scenario 3: Memory Cleanup Effectiveness
**Actor**: Operations Engineer
**Context**: Validating memory cleanup after code changes
**Flow**:
1. Engineer deploys updated Pylantir version with memory leak fixes
2. Monitors memory usage through logs and system metrics
3. Observes cleanup logs showing effective memory recovery
4. Confirms memory freed matches expected cleanup patterns
5. Validates long-term stability through extended monitoring

**Success Criteria**:
- Cleanup logs report > 0MB freed per cleanup cycle
- Garbage collector reports collected objects (> 0 count)
- Memory "before" and "after" measurements show measurable reduction
- Process memory (RSS) decreases or stabilizes after cleanup

## Functional Requirements

### FR-1: DataFrame Lifecycle Management
**Description**: Explicitly manage pandas DataFrame lifecycle to prevent memory retention

**Requirements**:
- FR-1.1: Convert DataFrames to native Python data structures immediately after use
- FR-1.2: Explicitly delete DataFrame variables using `del` before garbage collection
- FR-1.3: Clear DataFrame indices and caches before deletion
- FR-1.4: Use DataFrame iterator methods to avoid creating full copies

**Acceptance Criteria**:
- All DataFrame variables are explicitly deleted after processing
- No DataFrame references persist after `fetch_redcap_entries()` completes
- Memory profiling shows DataFrame memory is released within 1 GC cycle

### FR-2: REDCap API Client Cleanup
**Description**: Properly cleanup PyCap Project objects and their internal caches

**Requirements**:
- FR-2.1: Create new Project instance for each sync operation (avoid reuse)
- FR-2.2: Clear any internal caches in Project objects before deletion
- FR-2.3: Explicitly delete Project instance after data export completes
- FR-2.4: Investigate and clear PyCap's internal request/response cache

**Acceptance Criteria**:
- New Project instance created per sync cycle
- Project object and its caches are fully released after sync
- No accumulated HTTP response data in memory

### FR-3: SQLAlchemy Session Scoping
**Description**: Implement proper session scoping to prevent ORM object retention

**Requirements**:
- FR-3.1: Use scoped sessions with explicit removal after use
- FR-3.2: Call `session.expunge_all()` before session close to detach all ORM objects
- FR-3.3: Clear identity map after each synchronization cycle
- FR-3.4: Implement session-per-operation pattern (create fresh session per sync)

**Acceptance Criteria**:
- All ORM objects detached from session before close
- Identity map cleared, releasing object references
- Memory profiling shows WorklistItem objects are garbage collected

### FR-4: Connection Pool Management
**Description**: Configure and manage SQLAlchemy connection pool to prevent unbounded growth

**Requirements**:
- FR-4.1: Set explicit pool size limits (max_overflow=5, pool_size=10)
- FR-4.2: Enable pool pre-ping to detect stale connections
- FR-4.3: Configure pool recycle time (pool_recycle=3600) to refresh connections
- FR-4.4: Implement connection pool monitoring and logging

**Acceptance Criteria**:
- Connection pool size remains bounded (≤ 15 connections)
- Stale connections are automatically detected and recycled
- Pool metrics logged showing stable connection count

### FR-5: Enhanced Memory Cleanup Function
**Description**: Improve cleanup_memory_and_connections() effectiveness

**Requirements**:
- FR-5.1: Add explicit cleanup of module-level caches (pandas, SQLAlchemy)
- FR-5.2: Clear thread-local storage if present
- FR-5.3: Force multiple GC cycles targeting specific generations (0, 1, 2)
- FR-5.4: Add memory profiling to identify largest retained objects
- FR-5.5: Implement emergency cleanup threshold (if memory > 500MB, aggressive cleanup)

**Acceptance Criteria**:
- Cleanup function reports measurable memory freed (> 0MB per cycle)
- Garbage collector successfully collects objects (count > 0)
- Emergency cleanup triggers when memory exceeds threshold
- Logging shows specific object types being cleaned up

### FR-6: Memory Monitoring & Alerting
**Description**: Enhance memory monitoring to detect and alert on memory growth trends

**Requirements**:
- FR-6.1: Track memory usage over time (maintain rolling window of last 100 measurements)
- FR-6.2: Calculate memory growth rate (MB/hour)
- FR-6.3: Log warning when memory growth exceeds threshold (> 10MB/hour)
- FR-6.4: Log critical alert when absolute memory exceeds limit (> 500MB)
- FR-6.5: Include memory trend data in logs (current, average, max, growth rate)

**Acceptance Criteria**:
- Memory trends logged every 10 sync cycles
- Warnings appear when growth rate is abnormal
- Critical alerts trigger before system instability
- Historical data helps diagnose future issues

### FR-7: Logging Optimization
**Description**: Prevent logging from retaining references to large data structures

**Requirements**:
- FR-7.1: Avoid logging entire DataFrame contents or large data structures
- FR-7.2: Log only summaries (record count, field list, not full data)
- FR-7.3: Use lazy evaluation for expensive log message formatting
- FR-7.4: Clear log handlers' buffers periodically

**Acceptance Criteria**:
- Log messages contain summaries only (no full DataFrames)
- Memory profiling shows no large objects retained by logging
- Log files remain manageable size

## Success Criteria

### Quantitative Metrics

1. **Memory Stability**: Process memory usage remains < 150MB after 7 days of continuous operation
2. **Memory Growth Rate**: Daily memory growth < 5MB/day during steady-state
3. **Cleanup Effectiveness**: Memory cleanup frees > 0MB per cycle, with measurable decrease in RSS
4. **Garbage Collection**: GC collects > 0 objects per cleanup cycle, indicating active memory reclamation
5. **Long-term Reliability**: Server runs 30+ days without restart due to memory issues
6. **Performance**: Sync cycle time remains < 5 seconds despite cleanup overhead

### Qualitative Metrics

1. **Operational Stability**: No manual server restarts required due to memory pressure
2. **Log Quality**: Memory cleanup logs provide actionable insights (what was freed, how much)
3. **Production Confidence**: System administrators trust server to run unattended
4. **Healthcare Compliance**: Meets healthcare uptime requirements (99.9% availability)
5. **User Satisfaction**: Clinical imaging workflows uninterrupted by server issues

### Verification Methods

1. **Load Testing**: Run server with simulated REDCap data for 7+ days, monitor memory
2. **Memory Profiling**: Use memory_profiler and objgraph to verify object release
3. **Production Monitoring**: Deploy to test environment, monitor actual usage patterns
4. **Log Analysis**: Analyze cleanup logs to confirm effective memory recovery
5. **Stress Testing**: Test with 1000+ record syncs, verify memory remains stable

## Key Entities

### WorklistItem (ORM Object)
- **Lifecycle**: Created during sync, persisted to database, should be detached and GC'd
- **Issue**: References retained by SQLAlchemy identity map
- **Solution**: Explicit expunge and session cleanup

### REDCap DataFrame
- **Lifecycle**: Created by PyCap export, processed, should be deleted immediately
- **Issue**: References retained by groupby operations and pandas internal caches
- **Solution**: Explicit deletion and cache clearing

### PyCap Project
- **Lifecycle**: Created per sync, makes API calls, should be deleted after use
- **Issue**: Internal caches may retain HTTP responses
- **Solution**: Create new instance per sync, explicit deletion

### SQLAlchemy Connection
- **Lifecycle**: Managed by connection pool, should be recycled periodically
- **Issue**: Pool may grow unbounded, stale connections accumulate
- **Solution**: Configure pool limits and recycling

## Technical Constraints

### Must Not Break

- **DICOM Compliance**: Memory fixes must not affect DICOM MWL/MPPS service behavior
- **Data Integrity**: All patient data synchronization must remain accurate
- **API Compatibility**: Changes must not break existing CLI interfaces
- **Configuration Format**: No changes to JSON configuration structure
- **Logging Format**: Maintain existing log format for monitoring tools

### Performance Requirements

- **Sync Performance**: Memory cleanup must not add > 1 second per sync cycle
- **Responsiveness**: DICOM service response time must remain < 200ms
- **Resource Usage**: CPU overhead for cleanup must be < 5%

### Dependencies Constraint

- **Core Dependencies Only**: Solution must use only existing core dependencies
- **No New Libraries**: Prefer code changes over adding memory profiling libraries to production
- **Optional psutil**: Enhanced monitoring can use psutil (already optional dependency)

## Assumptions

1. **System Resources**: Server has sufficient total memory (2GB+) available
2. **Python Version**: Running Python 3.8+ with standard garbage collector
3. **REDCap Data Volume**: Typical sync returns 50-200 records
4. **Sync Frequency**: Default 30-minute interval, but must handle 5-minute intervals
5. **Operating Environment**: Linux server with standard memory management

## Out of Scope

- **Alternative Databases**: Switching from SQLite to PostgreSQL (separate consideration)
- **Architecture Redesign**: Moving to microservices or containerized deployment
- **REDCap API Changes**: Modifying how REDCap serves data
- **Python Version Upgrade**: Upgrading to Python 3.11+ for performance gains
- **Monitoring Dashboard**: External memory monitoring tools or dashboards

## Risks & Mitigations

### Risk 1: Cleanup Overhead Impacts Performance
**Likelihood**: Medium | **Impact**: Low
**Mitigation**: Profile cleanup operations, optimize expensive operations, make cleanup asynchronous if needed

### Risk 2: Aggressive Cleanup Breaks References
**Likelihood**: Low | **Impact**: High
**Mitigation**: Thorough testing, phased rollout, maintain cleanup effectiveness logs

### Risk 3: Memory Leak Persists After Changes
**Likelihood**: Medium | **Impact**: High
**Mitigation**: Use memory profiling tools, implement incremental fixes, add comprehensive monitoring

### Risk 4: Production Deployment Disrupts Clinical Operations
**Likelihood**: Low | **Impact**: Critical
**Mitigation**: Deploy during maintenance window, have rollback plan, extensive pre-production testing

## Dependencies

- **Internal**: Depends on existing `redcap_to_db.py`, `db_setup.py`, `models.py`
- **External**: No new external dependencies
- **Configuration**: May add optional memory monitoring configuration parameters

## Notes

- Current implementation already has `cleanup_memory_and_connections()` but it's ineffective
- Memory profiling suggests the issue is reference retention, not lack of GC calls
- Healthcare production environment requires careful testing before deployment
- This is a **CRITICAL** fix affecting production stability and patient safety
