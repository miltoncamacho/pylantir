# Pylantir Configuration Enhancement: Configurable Users Database Path

## Enhancement Summary

**Enhancement**: Allow configuration of users authentication database path via `users_db_path` in configuration JSON file.

**Date**: 2025-11-18  
**Version**: Part of v0.2.0 FastAPI feature  
**Constitutional Impact**: Configuration Management enhancement only

## Problem Statement

Previously, the users authentication database path was automatically determined based on the main worklist database location. This created limitations for:

1. **Security Requirements**: Organizations may need to separate authentication data from medical data
2. **Backup Strategies**: Different backup schedules for authentication vs. worklist data  
3. **Storage Management**: Different storage tiers for different types of data
4. **Compliance**: Some regulations may require separation of user authentication from PHI

## Solution Implementation

### Configuration File Enhancement

**Before** (Automatic Location):
```json
{
  "db_path": "/path/to/worklist.db"
  // users.db automatically created in same directory
}
```

**After** (Configurable):
```json
{
  "db_path": "/path/to/worklist.db",
  "users_db_path": "/secure/auth/users.db"  // Optional custom path
}
```

### Configuration Precedence

The system now follows this precedence order for users database location:

1. **Configuration File**: `users_db_path` in JSON config
2. **Environment Variable**: `USERS_DB_PATH` 
3. **Automatic Default**: `users.db` in same directory as main database

### Implementation Details

**Files Modified**:
- `src/pylantir/auth_db_setup.py`: Enhanced to accept configurable path
- `src/pylantir/cli/run.py`: Updated to pass config path to auth functions
- `src/pylantir/api_server.py`: Updated startup to use configured path
- `tests/test_api.py`: Updated test setup for new environment variable
- `README.md`: Added comprehensive documentation

**Backward Compatibility**: ✅ **Maintained**
- Existing configurations continue to work unchanged
- Default behavior remains identical
- No breaking changes introduced

### Usage Examples

#### 1. Default Behavior (No Change Required)
```json
{
  "db_path": "/data/worklist.db"
}
```
Result: Users database at `/data/users.db`

#### 2. Custom Users Database Path
```json
{
  "db_path": "/data/worklist.db",
  "users_db_path": "/secure/authentication.db"
}
```
Result: 
- Worklist: `/data/worklist.db`
- Users: `/secure/authentication.db`

#### 3. Environment Variable Override
```bash
export USERS_DB_PATH="/custom/users.db"
pylantir start-api --pylantir_config config.json
```
Result: Uses environment variable regardless of config file

### Security Benefits

1. **Data Separation**: Authentication data can be stored separately from PHI
2. **Access Control**: Different file permissions for different databases
3. **Backup Isolation**: Separate backup strategies for user vs. medical data
4. **Compliance**: Easier to meet regulatory requirements for data segregation

### CLI Command Updates

All user management CLI commands now respect the configured users database path:

```bash
# Commands automatically use configured users_db_path
pylantir admin-password --pylantir_config /path/to/config.json
pylantir create-user --pylantir_config /path/to/config.json
pylantir list-users --pylantir_config /path/to/config.json
```

## Constitutional Compliance

### ✅ Configuration Management Principle
- **Compliant**: Enhances existing configuration system without breaking changes
- **Backwards Compatible**: All existing configurations continue to work
- **Validation**: Configuration parsing validates new optional field
- **Documentation**: Complete documentation of new configuration option

### ✅ Healthcare Data Integrity  
- **Enhanced**: Allows better separation of authentication from PHI data
- **Audit Trails**: All database operations continue to be logged
- **Data Protection**: Enables more granular access control strategies

### ✅ Operational Observability
- **Maintained**: All logging continues to work
- **Enhanced**: Database paths are logged for transparency
- **Configuration**: Database locations clearly documented in logs

## Testing

**Test Coverage Added**:
- ✅ Environment variable precedence testing
- ✅ Configuration file parsing for `users_db_path`
- ✅ Backward compatibility verification
- ✅ CLI command integration testing

**Manual Testing Scenarios**:
```bash
# Test 1: Default behavior
pylantir start-api

# Test 2: Configuration file path
pylantir start-api --pylantir_config config_with_users_path.json

# Test 3: Environment variable override
export USERS_DB_PATH="/tmp/test_users.db"
pylantir start-api --pylantir_config config.json
```

## Documentation Updates

**README.md Sections Updated**:
- Configuration JSON file structure
- API Configuration section with precedence explanation
- CLI options documentation
- Security considerations

**New Documentation Added**:
- Database configuration options with examples
- Configuration precedence explanation
- Directory structure examples for different setups

---

**Enhancement Status**: ✅ **Complete**  
**Constitutional Impact**: Configuration enhancement only - no principle violations  
**Backward Compatibility**: ✅ **Maintained**  
**Testing**: ✅ **Comprehensive**  
**Documentation**: ✅ **Complete**