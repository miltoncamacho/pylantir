<div style="text-align: center;">
    <h1>Pylantir</h1>
</div>
<div style="text-align: center;">
    <img src="pylantir.png" alt="Pylantir" width="50%">
</div>

This project's goal is to significantly reduce the number of human-related errors when manualy registering participants for medical imaging procedures.

It effectively provides a python based DICOM Modality Worklist Server (SCP) and Modality Performed Procedure Step (SCP) able to receive requests from medical imaging equipemnt based on DICOM network comunication (e.g., a C-FIND, N-CREATE, N-SET requests).

It will build/update a database based on the information entered in the study-related REDCap database using a REDCap API (You will require to have API access to the study).

## Getting Started

To get started simply install using:

```bash
pip install pylantir
```

### Optional Dependencies

Pylantir offers several optional dependency groups for enhanced functionality:

#### API Support
For REST API and web interface capabilities:
```bash
pip install pylantir[api]
```
Includes: FastAPI, Uvicorn, JWT authentication, password hashing

#### Memory Monitoring (Recommended for Production)
For enhanced memory usage monitoring and cleanup during REDCap synchronization:
```bash
pip install pylantir[monitoring]
```
Includes: psutil for system resource monitoring

**Note**: While memory cleanup functions work without psutil, you need it installed to see cleanup effectiveness in logs. Without psutil, logs will show high-water mark memory values that don't decrease, even though cleanup is working. For production deployments, installing `[monitoring]` is **highly recommended** to validate memory stability.

#### Big Data Processing
For Spark-based data processing capabilities:
```bash
pip install pylantir[spark]
```
Includes: PySpark for large-scale data processing

#### Multiple Options
Install multiple optional dependency groups:
```bash
# API + Memory Monitoring
pip install pylantir[api,monitoring]

# All optional dependencies
pip install pylantir[api,monitoring,spark]
```

#### Development and Testing
For running tests and development:
```bash
pip install pylantir[test]
```
Includes: pytest, coverage tools, and testing utilities

You need to provide your REDCap API URL and API token before starting the server.
Set up environmental variables before starting the server:

```bash
export REDCAP_API_URL=<your API url>
export REDCAP_API_TOKEN=<your API token>
```

Start a server called with AEtitle MWL_SERVER.

```bash
pylantir start --ip 127.0.0.1 --port 4242 --AEtitle MWL_SERVER --pylantir_config Path/to/your/config.json
```

## Tests

If you want to run the tests make sure to clone the repository and run them from there.

Git clone the repository:

```bash
git clone https://github.com/miltoncamacho/pylantir
cd pylantir/tests
```

Query the worklist database to check that you have some entries using:

```bash
python query-db.py
```

Then, you can get a StudyUID from one of the entries to test the MPPS workflow. For example: 1.2.840.10008.3.1.2.3.4.55635351412689303463019139483773956632

Take this and run a create action to mark the worklist Procedure Step Status as IN_PROGRESS

```bash
python test-mpps.py --AEtitle MWL_SERVER --mpps_action create --callingAEtitle MWL_TESTER --ip 127.0.0.1 --port 4242 --study_uid 1.2.840.10008.3.1.2.3.4.55635351412689303463019139483773956632
```

You can verify that this in fact modified your database re-running:

```bash
python query-db.py
```

Finally, you can also simulate the pocedure completion efectively updating the Procedure Step Status to COMPLETED or DISCONTINUED:

```bash
python test-mpps.py --AEtitle MWL_SERVER --mpps_action set --mpps_status COMPLETED --callingAEtitle MWL_TESTER --ip 127.0.0.1 --port 4242 --study_uid 1.2.840.10008.3.1.2.3.4.55635351412689303463019139483773956632 --sop_uid 1.2.840.10008.3.1.2.3.4.187176383255263644225774937658729238426
```

## Usage

```bash
usage: pylantir [-h] [--AEtitle AETITLE] [--ip IP] [--port PORT] [--pylantir_config PYLANTIR_CONFIG] [--mpps_action {create,set}] [--mpps_status {COMPLETED,DISCONTINUED}] [--callingAEtitle CALLINGAETITLE] [--study_uid STUDY_UID] [--sop_uid SOP_UID] {start,query-db,test-client,test-mpps}
```

**pylantir** - Python DICOM Modality WorkList and Modality Performed Procedure Step compliance

### Positional Arguments:

- **{start,query-db,test-client,test-mpps,start-api,admin-password,create-user,list-users}**: Command to run:
  - **start**: Start the MWL server
  - **query-db**: Query the MWL database
  - **test-client**: Run tests for MWL
  - **test-mpps**: Run tests for MPPS
  - **start-api**: Start the FastAPI server (requires [api] dependencies)
  - **admin-password**: Change admin password
  - **create-user**: Create a new user (admin only)
  - **list-users**: List all users (admin only)

### Options:

- **-h, --help**: Show this help message and exit
- **--AEtitle AETITLE**: AE Title for the server
- **--ip IP**: IP/host address for the server
- **--port PORT**: Port for the server
- **--pylantir_config PYLANTIR_CONFIG**: Path to the configuration JSON file containing pylantir configs:
  - **data_sources**: Array of data source configurations (recommended new format)
    - Each source has: `name`, `type`, `enabled`, `sync_interval`, `operation_interval`, `config`, `field_mapping`
  - **redcap2wl**: Legacy field mapping (deprecated, auto-converts to data_sources)
  - **allowed_aet**: List of allowed AE titles e.g. `["MRI_SCANNER", "MRI_SCANNER_2"]`
  - **site**: Site ID (legacy format, deprecated)
  - **protocol**: `{"site": "protocol_name", "mapping": "HIS/RIS mapping"}`
  - **db_path**: Path to main worklist database e.g., `"/path/to/worklist.db"`
  - **users_db_path**: Optional path to users authentication database e.g., `"/path/to/users.db"`
  - **db_update_interval**: Legacy sync interval (deprecated, use sync_interval in data_sources)
  - **operation_interval**: Legacy operation window (deprecated, use operation_interval in data_sources)
- **--mpps_action {create,set}**: Action to perform for MPPS either create or set
- **--mpps_status {COMPLETED,DISCONTINUED}**: Status to set for MPPS either COMPLETED or DISCONTINUED
- **--callingAEtitle CALLINGAETITLE**: Calling AE Title for MPPS, it helps when the MWL is limited to only accept certain AE titles
- **--study_uid STUDY_UID**: StudyInstanceUID to test MPPS
- **--sop_uid SOP_UID**: SOPInstanceUID to test MPPS

## Configuration JSON file

Pylantir supports a modular data sources configuration that allows you to connect to multiple data sources simultaneously.

### New Data Sources Format (Recommended)

The new configuration format uses a `data_sources` array to define one or more data sources:

```json
{
  "db_path": "/path/to/worklist.db",
  "users_db_path": "/path/to/users.db",
  "db_echo": "False",
  "allowed_aet": [],
  "data_sources": [
    {
      "name": "main_redcap",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 60,
      "operation_interval": {
        "start_time": [0, 0],
        "end_time": [23, 59]
      },
      "config": {
        "site_id": "792",
        "protocol": "BRAIN_MRI_3T"
      },
      "field_mapping": {
        "study_id": "study_id",
        "instrument": "redcap_repeat_instrument",
        "session_id": "mri_instance",
        "family_id": "family_id",
        "youth_dob_y": "youth_dob_y",
        "t1_date": "t1_date",
        "demo_sex": "demo_sex",
        "scheduled_date": "mri_date",
        "scheduled_time": "mri_time",
        "mri_wt_lbs": "patient_weight_lb",
        "referring_physician": "referring_physician_name",
        "performing_physician": "performing_physician",
        "station_name": "station_name",
        "status": "performed_procedure_step_status"
      }
    }
  ],
  "protocol": {
    "792": "BRAIN_MRI_3T",
    "mapping": "GEHC"
  }
}
```

**Data Source Configuration Fields:**

- **`name`**: Unique identifier for this data source (used in logs and database tracking)
- **`type`**: Data source type (currently supports `"redcap"`; extensible for future sources)
- **`enabled`**: Boolean to enable/disable this source without removing its configuration
- **`sync_interval`**: How often to sync data (in seconds)
- **`operation_interval`**: Time window when sync should occur (24-hour format)
  - `start_time`: `[hours, minutes]` - Start of operation window
  - `end_time`: `[hours, minutes]` - End of operation window
- **`config`**: Source-specific configuration
  - For REDCap: `site_id`, `protocol`, and optional API credentials
- **`field_mapping`**: Maps source fields to DICOM worklist fields

### Multiple Data Sources Example

You can configure multiple data sources to sync simultaneously:

```json
{
  "db_path": "/path/to/worklist.db",
  "data_sources": [
    {
      "name": "site_792_redcap",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 60,
      "config": {
        "site_id": "792",
        "protocol": "BRAIN_MRI_3T"
      },
      "field_mapping": { "study_id": "study_id" }
    },
    {
      "name": "site_793_redcap",
      "type": "redcap",
      "enabled": true,
      "sync_interval": 120,
      "config": {
        "site_id": "793",
        "protocol": "CARDIAC_MRI"
      },
      "field_mapping": { "patient_id": "patient_id" }
    }
  ]
}
```

### Legacy Configuration Format (Deprecated)

⚠️ **The legacy configuration format is deprecated but still supported for backward compatibility.**

If you're using the old format, Pylantir will automatically convert it to the new format at runtime:

```json
{
  "db_path": "/path/to/worklist.db",
  "db_echo": "False",
  "db_update_interval": 60,
  "operation_interval": {"start_time": [0,0], "end_time": [23,59]},
  "site": "792",
  "redcap2wl": {
    "study_id": "study_id",
    "demo_sex": "demo_sex"
  },
  "protocol": {
    "792": "BRAIN_MRI_3T"
  }
}
```

When using the legacy format, you'll see a deprecation warning:
```
WARNING: Legacy configuration format detected.
Consider migrating to 'data_sources' format for better flexibility.
```

**Migration Note**: To migrate from legacy to new format:
1. Rename `redcap2wl` → `field_mapping`
2. Move `site` → `config.site_id`
3. Move `protocol[site]` → `config.protocol`
4. Move `db_update_interval` → `sync_interval`
5. Wrap everything in a `data_sources` array with `name`, `type`, and `enabled` fields

See `config/mwl_config_multi_source_example.json` for a complete example.

### Memory Management (Optional)

When you install the `monitoring` optional dependency (`pip install pylantir[monitoring]`), Pylantir gains enhanced memory monitoring capabilities during REDCap synchronization:

- **Automatic Memory Cleanup**: Performs garbage collection after each sync cycle
- **Memory Usage Reporting**: Logs current memory usage before and after cleanup
- **Connection Management**: Properly closes database connections and clears session caches
- **Resource Monitoring**: Tracks system resource usage during long-running operations

This is particularly useful for production deployments with frequent synchronization intervals or large datasets, helping prevent memory leaks during continuous operation.

**Memory monitoring works automatically** - no additional configuration required. The system will use enhanced monitoring when `psutil` is available, and fall back to basic garbage collection when it's not installed.

## FastAPI REST API (Optional)

**New in v0.2.0**: Pylantir now includes an optional REST API for programmatic access to worklist data and user management.

### Installation with API Support

To use the API features, install with optional API dependencies:

```bash
pip install pylantir[api]
```

This installs additional dependencies:
- `fastapi>=0.104.1`: Modern web framework for building APIs
- `uvicorn[standard]>=0.24.0`: ASGI server for running FastAPI
- `passlib[bcrypt]==1.7.4`: Password hashing library
- `bcrypt==4.0.1`: Bcrypt hashing algorithm
- `python-jose[cryptography]==3.5.0`: JWT token handling
- `python-multipart>=0.0.6`: Form data parsing

### Starting the API Server

```bash
# Start API server on default port (8000)
pylantir start-api --api-host 0.0.0.0 --api-port 8000

# With custom configuration
pylantir start-api --pylantir_config /path/to/config.json --api-port 8080
```

The API server will be available at:
- **API Endpoints**: `http://localhost:8000`
- **Interactive Documentation**: `http://localhost:8000/docs` (Swagger UI)
- **Alternative Documentation**: `http://localhost:8000/redoc` (ReDoc)

### Authentication & Authorization

The API uses JWT (JSON Web Token) authentication with role-based access control:

#### User Roles:
- **admin**: Full access to users and worklist data (CRUD operations)
- **write**: Read and write access to worklist data only
- **read**: Read-only access to worklist data only

#### Initial Setup:
On first run, a default admin user is created:
- **Username**: `admin`
- **Password**: `admin123`

⚠️ **Change the default password immediately:**

```bash
pylantir admin-password --username admin
```

### API Endpoints

#### Authentication
- `POST /auth/login`: Authenticate and receive JWT token

#### Worklist Management
- `GET /worklist`: Retrieve worklist items with filtering
- `POST /worklist`: Create new worklist items (write/admin)
- `PUT /worklist/{id}`: Update worklist items (write/admin)
- `DELETE /worklist/{id}`: Delete worklist items (write/admin)

#### User Management (Admin Only)
- `GET /users`: List all users
- `POST /users`: Create new users
- `PUT /users/{id}`: Update users
- `DELETE /users/{id}`: Delete users

#### Health Check
- `GET /health`: API health status

### API Usage Examples

#### 1. Login and Get Token

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "your_new_password",
    "access_token_expire_minutes": 60
  }'
```

You can optionally send `access_token_expire_minutes` in the login payload to override the default TTL that is applied to newly minted tokens.

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### 2. Get Worklist Items

```bash
# Get all scheduled and in-progress items (default)
curl -X GET "http://localhost:8000/worklist" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Filter by specific status
curl -X GET "http://localhost:8000/worklist?status=SCHEDULED&status=COMPLETED" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Filter by patient ID
curl -X GET "http://localhost:8000/worklist?patient_id=PATIENT001" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### 3. Create Worklist Item

```bash
curl -X POST "http://localhost:8000/worklist" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_name": "Doe^John",
    "patient_id": "PATIENT001",
    "patient_birth_date": "19900101",
    "patient_sex": "M",
    "modality": "MR",
    "performed_procedure_step_status": "SCHEDULED"
  }'
```

#### 4. Update Procedure Status

```bash
curl -X PUT "http://localhost:8000/worklist/1" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"performed_procedure_step_status": "IN_PROGRESS"}'
```

### CLI User Management

#### Change Admin Password

```bash
pylantir admin-password --username admin
# Prompts for current and new password
```

#### Create New User

```bash
pylantir create-user --username newuser --role write --email user@example.com
# Prompts for admin credentials and new user password
```

#### List Users

```bash
pylantir list-users
# Prompts for admin credentials, then displays user table
```

### Python Client Example

```python
import requests

# Login
response = requests.post("http://localhost:8000/auth/login", json={
    "username": "admin",
  "password": "your_password",
  "access_token_expire_minutes": 120
})
token = response.json()["access_token"]

# Set headers for authenticated requests
headers = {"Authorization": f"Bearer {token}"}

# Get worklist items
response = requests.get("http://localhost:8000/worklist", headers=headers)
worklist_items = response.json()

# Create new item
new_item = {
    "patient_name": "Smith^Jane",
    "patient_id": "PATIENT002",
    "modality": "CT",
    "performed_procedure_step_status": "SCHEDULED"
}
response = requests.post("http://localhost:8000/worklist",
                        json=new_item, headers=headers)
```

### API Configuration

The API server uses the same configuration file as the main DICOM server for database settings. You can configure both the main worklist database and the users authentication database paths.

#### Database Configuration Options:

1. **Automatic Location (Default)**:
   ```json
   {
     "db_path": "/path/to/worklist.db"
   }
   ```
   - Users database will be created as `users.db` in the same directory
   - Result: `/path/to/users.db`

2. **Custom Users Database Path**:
   ```json
   {
     "db_path": "/path/to/worklist.db",
     "users_db_path": "/different/path/to/authentication.db"
   }
   ```
   - Users database will be created at the specified location
   - Allows separation of databases for security or organizational reasons

3. **Environment Variable Override**:
   ```bash
   export USERS_DB_PATH="/custom/path/to/users.db"
   ```
   - Takes precedence over configuration file setting
   - Useful for deployment-specific configurations

#### Configuration Precedence:
1. `users_db_path` in configuration JSON file
2. `USERS_DB_PATH` environment variable
3. Default: `users.db` in same directory as main database

Example directory structures:

**Default Setup:**
```
/path/to/databases/
├── worklist.db      # Main DICOM worklist database
└── users.db         # API authentication database (auto-created)
```

**Custom Setup:**
```
/path/to/databases/
├── worklist.db      # Main DICOM worklist database

/secure/auth/
└── authentication.db # API authentication database (custom path)
```

#### CORS Configuration

Control Cross-Origin Resource Sharing (CORS) for web frontend integration:

```json
{
  "db_path": "/path/to/worklist.db",
  "api": {
    "cors_allowed_origins": [
      "http://localhost:3000",
      "http://localhost:8080",
      "https://radiology-dashboard.hospital.local",
      "https://your-frontend-domain.com"
    ],
    "cors_allow_credentials": true,
    "cors_allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "cors_allow_headers": ["*"]
  }
}
```

**CORS Configuration Options:**

- **`cors_allowed_origins`**: Array of allowed origin URLs for browser requests
  - Use specific domains for security (avoid `["*"]` in production)
  - Include all frontend application URLs that will access the API
  - Supports both HTTP (development) and HTTPS (production) origins

- **`cors_allow_credentials`**: Boolean, allows cookies/auth headers in CORS requests
  - Set to `true` for JWT token authentication (recommended)
  - Required for browser-based authentication

- **`cors_allow_methods`**: Array of allowed HTTP methods
  - Default: `["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
  - Include `"OPTIONS"` for preflight requests

- **`cors_allow_headers`**: Array of allowed request headers
  - Default: `["*"]` allows all headers
  - Can specify specific headers like `["Authorization", "Content-Type"]`

**CORS Security Best Practices:**
- Never use `["*"]` for origins in production environments
- Specify only the exact domains that need API access
- Use HTTPS origins for production deployments
- Regularly audit and update allowed origins list

**Example Production CORS Setup:**
```json
{
  "api": {
    "cors_allowed_origins": [
      "https://radiology.hospital.com",
      "https://dashboard.hospital.com"
    ],
    "cors_allow_credentials": true,
    "cors_allow_methods": ["GET", "POST", "PUT", "DELETE"],
    "cors_allow_headers": ["Authorization", "Content-Type"]
  }
}
```

### Security Considerations

- **Change Default Password**: Always change the default admin password
- **Use HTTPS**: In production, use HTTPS with proper SSL certificates
- **Network Security**: Restrict API access using firewalls/network policies
- **Token Management**: JWT tokens expire after 30 minutes by default
- **Database Permissions**: Ensure database files have appropriate file permissions

## Clean Stop of the MWL and Database Sync

To cleanly stop the MWL server and ensure the database syncronization properly, press `Ctrl + C` (you might need to press it twice).

To stop the API server, use `Ctrl + C` in the terminal where it's running.
