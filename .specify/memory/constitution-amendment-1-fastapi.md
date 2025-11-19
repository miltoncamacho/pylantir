# Pylantir Constitution - Amendment 1: FastAPI Integration
**Amendment to Pylantir Constitution v2.0.0**

## Amendment Summary

This amendment formally incorporates RESTful API capabilities into the Pylantir framework while maintaining constitutional compliance through optional dependency management and architectural separation.

## Constitutional Compliance Analysis

### I. Minimalist Dependencies ✅ **COMPLIANT**
- API dependencies added as **optional** package group `[api]`
- Core DICOM functionality remains dependency-minimal
- Users can install base package without API overhead
- Clear separation between core and extended functionality

### II. CLI-First Design ✅ **COMPLIANT** 
- All API functionality accessible via CLI commands:
  - `pylantir start-api`: Launch API server
  - `pylantir admin-password`: Password management
  - `pylantir create-user`: User creation
  - `pylantir list-users`: User management
- API serves as secondary interface, not replacement for CLI
- Configuration maintained via JSON files and environment variables

### III. Healthcare Data Integrity ✅ **COMPLIANT**
- JWT authentication with role-based access control
- Separate authentication database with encrypted passwords
- All database operations use SQLAlchemy ORM patterns
- Comprehensive audit logging for API operations
- Input validation and sanitization at API layer

### IV. Test-Driven Integration ✅ **COMPLIANT**
- Comprehensive integration tests for API endpoints
- Authentication and authorization testing
- Mock database setup for isolated testing
- Role-based permission validation tests

### V. Operational Observability ✅ **COMPLIANT**
- Structured logging for all API operations
- User authentication audit trails
- Database operation logging
- Health check endpoints for monitoring

## New Architectural Components

### Authentication Layer
```
src/pylantir/
├── auth_models.py      # User authentication models
├── auth_utils.py       # Password hashing, JWT handling
├── auth_db_setup.py    # Separate authentication database
└── api_server.py       # FastAPI application with endpoints
```

### API Service Architecture
- **RESTful Endpoints**: Standard HTTP methods (GET, POST, PUT, DELETE)
- **JWT Authentication**: Stateless token-based authentication
- **Role-Based Access**: Admin, Write, Read permission levels
- **Database Separation**: Isolated authentication database
- **OpenAPI Documentation**: Auto-generated API documentation

### Security Framework
- **Password Hashing**: bcrypt with configurable rounds
- **JWT Tokens**: 30-minute expiration with proper signing
- **Role Validation**: Middleware-based permission checking  
- **Input Validation**: Pydantic models for request/response validation

## Version Impact

- **Version Bump**: 0.1.3 → 0.2.0 (MINOR)
- **Rationale**: New features, backwards-compatible functionality
- **Breaking Changes**: None
- **Migration Required**: None

## Optional Dependency Specification

```toml
[project.optional-dependencies]
api = [
    "fastapi>=0.104.1",
    "uvicorn[standard]>=0.24.0", 
    "passlib[bcrypt]==1.7.4",
    "bcrypt==4.0.1",
    "python-jose[cryptography]==3.5.0",
    "python-multipart>=0.0.6"
]
```

## Constitutional Updates Required

### Core Principles Amendment
Update **Minimalist Dependencies** principle to explicitly allow optional dependency groups for extended functionality while maintaining core simplicity.

### Technical Architecture Extension  
Add **API Layer Architecture** section documenting:
- RESTful endpoint specifications
- Authentication and authorization patterns
- Database separation requirements
- Security implementation standards

### Development Standards Enhancement
Add **API Development Standards** covering:
- FastAPI application structure
- Pydantic model definitions
- Authentication middleware patterns
- API testing requirements

## Future Roadmap Alignment

### Allowed Enhancements ✅
- ✅ Web-based monitoring dashboard (separate package) 
- ✅ Additional data sources beyond REDCap (with approval)
- ✅ Enhanced DICOM service capabilities
- ✅ Performance optimizations and caching

### Prohibited Additions ❌
- ❌ GUI applications or desktop interfaces
- ❌ Heavy dependencies (web frameworks as core requirements)
- ❌ Direct integration beyond DICOM
- ❌ Patient data analytics within core package

## Amendment Approval

**Constitutional Compliance**: ✅ **APPROVED**
- Maintains all five core principles
- Follows architectural constraints
- Meets development standards
- Adheres to governance framework

**Implementation Status**: ✅ **COMPLETE**
- All code components implemented
- Tests created and passing
- Documentation updated
- CLI integration complete

---

**Amendment Version**: 1.0  
**Proposed**: 2025-11-18  
**Approved**: 2025-11-18  
**Effective**: 2025-11-18  
**Next Review**: 2026-05-18  

**Approver**: Milton Camacho (Project Lead)  
**Constitutional Impact**: Extends framework capabilities while maintaining compliance