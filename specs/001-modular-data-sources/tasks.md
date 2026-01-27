# Tasks: Modular Data Source Architecture

**Input**: Design documents from `/specs/001-modular-data-sources/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/plugin-interface.py, quickstart.md

**Tests**: Not explicitly requested in specification - focusing on implementation with test infrastructure

**Organization**: Tasks grouped by user story (US1: Refactor REDCap, US2: Multi-source support, US3: Plugin extensibility)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize plugin architecture directory structure and base configuration

**Duration Estimate**: 30 minutes

- [x] T001 Create `src/pylantir/data_sources/` directory for plugin implementations
- [x] T002 Create `tests/` directory for plugin-related tests (if not exists)
- [x] T003 [P] Copy contracts/plugin-interface.py to src/pylantir/data_sources/base.py as implementation template
- [x] T004 [P] Create example multi-source configuration in config/mwl_config_multi_source_example.json

**Checkpoint**: ✅ Directory structure ready for plugin development

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core plugin infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

**Duration Estimate**: 2-3 hours

- [x] T005 Implement DataSourcePlugin ABC in src/pylantir/data_sources/base.py with all abstract methods (validate_config, fetch_entries, get_source_name)
- [x] T006 [P] Implement plugin exceptions (PluginError, PluginConfigError, PluginFetchError) in src/pylantir/data_sources/base.py
- [x] T007 Create plugin registry system in src/pylantir/data_sources/__init__.py with PLUGIN_REGISTRY dict and get_plugin() function
- [x] T008 Add data_source field to WorklistItem model in src/pylantir/models.py (String, nullable=True, default=None)
- [x] T009 [P] Create database migration script migrations/001_add_data_source_field.sql for data_source column addition
- [x] T010 [P] Update load_config() function in src/pylantir/cli/run.py to support both legacy and new data_sources format
- [x] T011 Implement legacy config auto-conversion logic in src/pylantir/cli/run.py (detect redcap2wl, convert to data_sources array)

**Checkpoint**: ✅ Foundation ready - plugin implementations and multi-source orchestration can now proceed

---

## Phase 3: User Story 1 - Refactor REDCap as Plugin (Priority: P1) 🎯 MVP

**Goal**: Extract REDCap sync logic into first plugin implementation, maintaining 100% backward compatibility

**Independent Test**: Configure legacy REDCap config, start Pylantir, verify worklist populates with auto-conversion warning

**Duration Estimate**: 4-6 hours

### Implementation for User Story 1

- [x] T012 [US1] Create REDCapPlugin class in src/pylantir/data_sources/redcap_plugin.py inheriting from DataSourcePlugin ✅
- [x] T013 [US1] Implement validate_config() method in REDCapPlugin to check site_id and protocol keys ✅
- [x] T014 [US1] Extract fetch_redcap_entries() logic from src/pylantir/redcap_to_db.py into REDCapPlugin.fetch_entries() method ✅
- [x] T015 [US1] Extract field mapping logic into REDCapPlugin._apply_field_mapping() helper method ✅
- [x] T016 [US1] Implement get_source_name() in REDCapPlugin to return "REDCap" ✅
- [x] T017 [US1] Override supports_incremental_sync() in REDCapPlugin to return True ✅
- [x] T018 [US1] Implement cleanup() in REDCapPlugin following memory efficiency patterns (gc.collect(), del PyCap objects) ✅
- [x] T019 [US1] Register REDCapPlugin in PLUGIN_REGISTRY dict in src/pylantir/data_sources/__init__.py ✅
- [x] T020 [US1] Create legacy wrapper in src/pylantir/redcap_to_db.py that imports and calls REDCapPlugin for backward compatibility ✅
- [x] T021 [US1] Add deprecation warning in redcap_to_db.py wrapper functions ✅
- [x] T022 [US1] Update sync_redcap_to_db() and sync_redcap_to_db_repeatedly() to use REDCapPlugin internally ✅
- [x] T023 [US1] Test legacy configuration auto-conversion with existing mwl_config.json files ✅
- [x] T024 [US1] Verify backward compatibility: existing configs work without modification ✅

**Checkpoint**: REDCap is now a plugin; legacy configs auto-convert and sync works identically ✅

---

## Phase 4: User Story 2 - Multi-Source Orchestration (Priority: P2)

**Goal**: Enable concurrent syncing from multiple configured data sources with isolated failure domains

**Independent Test**: Configure 2-3 REDCap sources with different sync_intervals, verify all sources populate database with proper source attribution

**Duration Estimate**: 3-4 hours

### Implementation for User Story 2

- [x] T025 [US2] Implement parse_data_sources_config() function in src/pylantir/cli/run.py to extract and validate data_sources array ✅
- [x] T026 [US2] Implement validate_source_config() function in src/pylantir/cli/run.py to check required fields (name, type, config, field_mapping) ✅
- [x] T027 [US2] Create sync_single_source() wrapper function in src/pylantir/cli/run.py that loads plugin, validates config, and calls sync loop ✅
- [x] T028 [US2] Implement multi-source orchestration using ThreadPoolExecutor in src/pylantir/cli/run.py main() function ✅
- [x] T029 [US2] Add per-source thread spawning logic with one thread per enabled data source ✅
- [x] T030 [US2] Implement per-source error handling with try/except around each plugin.fetch_entries() call ✅
- [x] T031 [US2] Add source name logging prefix to all plugin operations (e.g., "[REDCap:main_redcap]") ✅
- [x] T032 [US2] Update database insert logic to populate data_source field with source config name ✅
- [x] T033 [US2] Implement graceful shutdown for multiple source threads using existing STOP_EVENT pattern ✅
- [ ] T034 [US2] Test with configuration containing multiple REDCap sources (different sites/protocols)
- [ ] T035 [US2] Verify source isolation: simulate one source failing, confirm others continue syncing
- [ ] T036 [US2] Test per-source sync intervals (different sources with different intervals run independently)

**Checkpoint**: Multiple sources sync concurrently with isolated failure domains and proper attribution

---

## Phase 5: User Story 3 - Plugin Extensibility (Priority: P3)

**Goal**: Document plugin interface and verify third-party developers can create custom plugins

**Independent Test**: Create minimal test plugin (10-20 lines), configure it, verify Pylantir syncs from it

**Duration Estimate**: 2-3 hours

### Implementation for User Story 3

- [ ] T037 [P] [US3] Create plugin development guide in docs/plugin-development.md based on quickstart.md
- [ ] T038 [P] [US3] Document DataSourcePlugin interface with examples in docs/plugin-development.md
- [ ] T039 [P] [US3] Create minimal example plugin (MockPlugin) in docs/examples/mock_plugin.py
- [ ] T040 [US3] Add plugin discovery validation in src/pylantir/cli/run.py (check type exists in PLUGIN_REGISTRY)
- [ ] T041 [US3] Improve error messages for missing/invalid plugin types in get_plugin() function
- [ ] T042 [US3] Add config validation error reporting with specific field names and values
- [ ] T043 [US3] Test MockPlugin: register it, configure it, verify it syncs successfully
- [ ] T044 [US3] Document plugin registration process in docs/plugin-development.md
- [ ] T045 [US3] Create plugin testing template in docs/examples/test_plugin_template.py

**Checkpoint**: Plugin interface is fully documented with working examples; third-party development enabled

---

## Phase 6: Testing & Validation

**Purpose**: Comprehensive testing of plugin architecture and migration scenarios

**Duration Estimate**: 3-4 hours

### Unit Tests

- [ ] T046 [P] Create tests/test_plugin_interface.py to validate DataSourcePlugin ABC (cannot instantiate, requires abstract methods)
- [ ] T047 [P] Create tests/test_redcap_plugin.py with mocked PyCap Project to test REDCapPlugin methods
- [ ] T048 [P] Test REDCapPlugin.validate_config() with valid and invalid configurations
- [ ] T049 [P] Test REDCapPlugin.fetch_entries() data transformation with mock REDCap data
- [ ] T050 [P] Test REDCapPlugin.cleanup() memory management

### Integration Tests

- [ ] T051 [P] Create tests/test_backward_compat.py to verify legacy config auto-conversion
- [ ] T052 [P] Test that auto-converted legacy config produces same sync behavior
- [ ] T053 [P] Verify deprecation warnings are logged for legacy configs
- [ ] T054 Create tests/test_multi_source_config.py to test multiple source parsing and validation
- [ ] T055 Test multi-source orchestration with 2-3 concurrent sources
- [ ] T056 Test source isolation: one source fails, others continue
- [ ] T057 Test data_source field population in database entries

### Memory & Performance Tests

- [ ] T058 [P] Create tests/test_plugin_memory.py to validate memory cleanup patterns
- [ ] T059 Test that memory usage stays constant across multiple sync cycles
- [ ] T060 Verify 50-100x memory efficiency vs pandas is maintained
- [ ] T061 Test concurrent source syncing doesn't cause memory leaks

**Checkpoint**: All tests passing, backward compatibility verified, performance maintained

---

## Phase 7: Documentation & Migration Support

**Purpose**: User-facing documentation and migration tooling

**Duration Estimate**: 2-3 hours

- [ ] T062 [P] Update README.md with migration guide section pointing to quickstart.md
- [ ] T063 [P] Add data_sources configuration examples to README.md
- [ ] T064 [P] Document environment variables required for REDCap plugin (REDCAP_API_URL, REDCAP_API_TOKEN)
- [ ] T065 [P] Create config/mwl_config_legacy_example.json showing old format
- [ ] T066 [P] Update config/mwl_config.json with new data_sources format as primary example
- [ ] T067 Create migration script tools/migrate_config.py to auto-convert legacy configs
- [ ] T068 Add --check-config CLI flag to validate configuration without starting server
- [ ] T069 Update FEATURE_SUMMARY.md with plugin architecture description
- [ ] T070 Add troubleshooting section to quickstart.md for common migration issues

**Checkpoint**: Users have clear migration path with tools and documentation

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Code quality, logging improvements, edge case handling

**Duration Estimate**: 2-3 hours

- [ ] T071 [P] Add detailed logging for plugin lifecycle (initialization, validation, fetch, cleanup)
- [ ] T072 [P] Implement config validation with helpful error messages (specify missing keys, invalid types)
- [ ] T073 [P] Add startup validation summary (list all enabled sources, their intervals, operation windows)
- [ ] T074 Handle edge case: empty data_sources array (error with helpful message)
- [ ] T075 Handle edge case: duplicate source names (error at validation time)
- [ ] T076 Handle edge case: unknown plugin type (error with list of available types)
- [ ] T077 Add memory usage logging if psutil available (per-source basis)
- [ ] T078 Implement clean error handling for plugin exceptions with source context
- [ ] T079 Add CLI warning if using legacy config format (suggest migration)
- [ ] T080 Code review: ensure all plugin code follows Pylantir Constitution principles
- [ ] T081 Performance profiling: verify no regression in sync performance
- [ ] T082 Final integration test: run Pylantir with multi-source config for 24 hours

**Checkpoint**: Production-ready plugin architecture with robust error handling and observability

---

## Dependencies & Execution Order

### Critical Path (Must Complete in Order)

1. **Phase 1 → Phase 2**: Setup before foundation
2. **Phase 2 → Phase 3**: Foundation before REDCap refactoring
3. **Phase 3 → Phase 4**: Single plugin working before multi-source orchestration
4. **Phase 4 → Phase 5**: Multi-source working before extensibility documentation

### User Story Independence

- ✅ **US1 (REDCap Plugin)**: Can be fully tested independently (Phase 3 checkpoint)
- ✅ **US2 (Multi-Source)**: Builds on US1 but independently testable (Phase 4 checkpoint)
- ✅ **US3 (Extensibility)**: Builds on US1+US2 but independently testable (Phase 5 checkpoint)

### Parallel Execution Opportunities

**Within Phase 2 (Foundation)**:
- T006 (Exceptions) || T009 (Migration script) || T010 (Config parsing) can run in parallel

**Within Phase 3 (US1 - REDCap Plugin)**:
- T012-T018 (Plugin implementation) can be developed incrementally
- T020-T021 (Legacy wrapper) can start once T012-T019 complete

**Within Phase 4 (US2 - Multi-Source)**:
- T025-T027 (Config validation) || T031 (Logging) can run in parallel
- T034-T036 (Testing) can run in parallel once T025-T033 complete

**Within Phase 6 (Testing)**:
- All unit tests (T046-T050) can run in parallel
- All integration tests (T051-T057) can run in parallel
- All memory tests (T058-T061) can run in parallel

**Within Phase 7 (Documentation)**:
- T062-T066 (Documentation) || T067-T068 (Migration tools) can run in parallel

**Within Phase 8 (Polish)**:
- T071-T073 (Logging) || T074-T076 (Edge cases) can run in parallel

---

## Implementation Strategy

### MVP Scope (Minimum Viable Product)

**Recommended MVP**: User Story 1 ONLY (Phase 1 + Phase 2 + Phase 3)

**Why**: Delivers core value (plugin architecture + REDCap refactoring) with backward compatibility in ~6-9 hours of work

**MVP Includes**:
- Plugin interface (DataSourcePlugin ABC)
- REDCap plugin implementation
- Legacy config auto-conversion
- Database source tracking field
- Backward compatibility verified

**MVP Excludes** (defer to Phase 2):
- Multi-source orchestration (US2)
- Plugin extensibility docs (US3)
- Comprehensive test suite
- Migration tooling

### Incremental Delivery Phases

**Delivery 1** (MVP - US1):
- Tasks T001-T024
- Deliverable: REDCap works as plugin, legacy configs work
- Time: 1-2 days

**Delivery 2** (US2):
- Tasks T025-T036
- Deliverable: Multiple sources sync concurrently
- Time: 1 day

**Delivery 3** (US3):
- Tasks T037-T045
- Deliverable: Plugin development guide + examples
- Time: 0.5 day

**Delivery 4** (Testing):
- Tasks T046-T061
- Deliverable: Comprehensive test coverage
- Time: 1 day

**Delivery 5** (Documentation & Polish):
- Tasks T062-T082
- Deliverable: Production-ready with docs
- Time: 1 day

**Total Time Estimate**: 4-5 days for complete feature

---

## Task Summary

**Total Tasks**: 82
- **Phase 1 (Setup)**: 4 tasks
- **Phase 2 (Foundation)**: 7 tasks
- **Phase 3 (US1 - REDCap Plugin)**: 13 tasks
- **Phase 4 (US2 - Multi-Source)**: 12 tasks
- **Phase 5 (US3 - Extensibility)**: 9 tasks
- **Phase 6 (Testing)**: 16 tasks
- **Phase 7 (Documentation)**: 9 tasks
- **Phase 8 (Polish)**: 12 tasks

**Parallelizable Tasks**: 35 tasks marked [P]

**User Story Breakdown**:
- **US1 (Refactor REDCap)**: 13 implementation tasks
- **US2 (Multi-Source)**: 12 implementation tasks
- **US3 (Extensibility)**: 9 implementation tasks

**Independent Test Criteria**:
- ✅ US1: Legacy config works, REDCap syncs via plugin
- ✅ US2: Multiple sources sync with isolation and attribution
- ✅ US3: MockPlugin can be created and used successfully

**Format Validation**: ✅ All tasks follow `- [ ] [ID] [P?] [Story?] Description` format

---

## Next Steps

1. **Start with MVP**: Implement Phase 1 + Phase 2 + Phase 3 (Tasks T001-T024)
2. **Validate US1**: Run tests, verify backward compatibility
3. **Proceed to US2**: Only after US1 checkpoint passes
4. **Complete in increments**: Deliver each user story independently
5. **Test continuously**: Run integration tests after each phase

**Ready for**: `/speckit.implement` to begin automated implementation
