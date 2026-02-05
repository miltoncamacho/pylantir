from __future__ import annotations

import argparse
import logging
import os
import json
import importlib.resources as pkg_resources
import pathlib as Path
import coloredlogs
import sys
import importlib.util
from dotenv import set_key
from concurrent.futures import ThreadPoolExecutor  # for background thread

lgr = logging.getLogger(__name__)

def setup_logging(debug=False):

    # Set the base level to DEBUG or INFO
    level = logging.DEBUG if debug else logging.INFO
    coloredlogs.install(level=level)
    logging.getLogger("pynetdicom").setLevel(logging.INFO)
    # Then forcibly suppress SQLAlchemy logs:
    logging.getLogger("sqlalchemy").handlers = [logging.NullHandler()]
    logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.orm").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.engine.Engine").handlers = [logging.NullHandler()]
    # or completely disable them:
    logging.getLogger("sqlalchemy.engine.Engine").disabled = True

def parse_args():
    default_config_path = str(pkg_resources.files("pylantir").joinpath("config/mwl_config.json"))

    p = argparse.ArgumentParser(description="pylantir - Python DICOM Modality WorkList and Modality Performed Procedure Step compliance")
    p.add_argument("command",
                    help="""
                        Command to run:
                        - start: start the MWL server
                        - query-db: query the MWL db
                        - test-client: run tests for MWL
                        - test-mpps: run tests for MPPS
                        - start-api: start the FastAPI server (requires [api] dependencies)
                        - admin-password: change admin password
                        - create-user: create a new user (admin only)
                        - list-users: list all users (admin only)
                    """,
                    choices=["start", "query-db", "test-client", "test-mpps",
                            "start-api", "admin-password", "create-user", "list-users"],
                    )
    p.add_argument("--AEtitle", help="AE Title for the server")
    p.add_argument("--ip", help="IP/host address for the server", default="0.0.0.0")
    p.add_argument("--port", type=int, help="port for the server", default=4242)

    p.add_argument(
        "--pylantir_config",
        type=str,
        help="""
                Path to the configuration JSON file containing pylantir configs:
                - allowed_aet: list of allowed AE titles e.g. ["MRI_SCANNER", "MRI_SCANNER_2"]
                - mri_visit_session_mapping: mapping of MRI visit to session e.g., {"T1": "1", "T2": "2"}
                - site: site ID:string
                - protocol: {"site": "protocol_name"}
                - redcap2wl: dictionary of redcap fields to worklist fields mapping e.g., {"redcap_field": "worklist_field"}
            """, #TODO: allow more usages
        default=None,
    )

    p.add_argument(
        "--mpps_action",
        choices=["create", "set"],
        default=None,
        help="Action to perform for MPPS either create or set",
    )

    p.add_argument(
        "--mpps_status",
        default=None,
        type=str,
        choices=["COMPLETED", "DISCONTINUED"],
        help="Status to set for MPPS either COMPLETED or DISCONTINUED",
    )

    p.add_argument(
        "--callingAEtitle",
        default=None,
        type=str,
        help="Calling AE Title for MPPS it helps when the MWL is limited to only accept certain AE titles",
    )

    p.add_argument(
        "--study_uid",
        default=None,
        type=str,
        help="StudyInstanceUID to test MPPS",
    )

    p.add_argument(
        "--sop_uid",
        default=None,
        type=str,
        help="SOPInstanceUID to test MPPS",
    )

    # API server arguments
    p.add_argument(
        "--api-host",
        default="0.0.0.0",
        type=str,
        help="API server host address (default: 0.0.0.0)"
    )

    p.add_argument(
        "--api-port",
        default=8000,
        type=int,
        help="API server port (default: 8000)"
    )

    # User management arguments
    p.add_argument(
        "--username",
        default=None,
        type=str,
        help="Username for user operations"
    )

    p.add_argument(
        "--password",
        default=None,
        type=str,
        help="Password for user operations"
    )

    p.add_argument(
        "--email",
        default=None,
        type=str,
        help="Email for user creation"
    )

    p.add_argument(
        "--full-name",
        default=None,
        type=str,
        help="Full name for user creation"
    )

    p.add_argument(
        "--role",
        default="read",
        choices=["admin", "write", "read"],
        help="User role (default: read)"
    )

    return p.parse_args()

def load_config(config_path=None):
    """
    Load configuration file, either from a user-provided path or the default package location.
    Auto-converts legacy configuration format to new data_sources format.

    Args:
        config_path (str | Path, optional): Path to the configuration JSON file.

    Returns:
        dict: Parsed JSON config as a dictionary.
    """
    if config_path is None:
        config_path = pkg_resources.files("pylantir").joinpath("config/mwl_config.json")

    config_path = Path.Path(config_path)  # Ensure it's a Path object

    try:
        with config_path.open("r") as f:
            config_data = json.load(f)
        lgr.info(f"Loaded configuration from {config_path}")

        # Auto-convert legacy configuration format
        if "data_sources" not in config_data and "redcap2wl" in config_data:
            lgr.warning(
                "Legacy configuration format detected. "
                "Consider migrating to 'data_sources' format for better flexibility. "
                "See config/mwl_config_multi_source_example.json for reference."
            )

            # Convert legacy format to data_sources array
            legacy_source = {
                "name": "redcap_legacy",
                "type": "redcap",
                "enabled": True,
                "sync_interval": config_data.get("db_update_interval", 60),
                "operation_interval": config_data.get(
                    "operation_interval",
                    {"start_time": [0, 0], "end_time": [23, 59]}
                ),
                "config": {
                    "site_id": config_data.get("site"),
                    "protocol": config_data.get("protocol", {}),
                },
                "field_mapping": config_data.get("redcap2wl", {})
            }

            config_data["data_sources"] = [legacy_source]
            lgr.info("Auto-converted legacy configuration to data_sources format")

        return config_data

    except FileNotFoundError:
        lgr.error(f"Configuration file '{config_path}' not found.")
        return {}

    except json.JSONDecodeError:
        lgr.error(f"Invalid JSON format in '{config_path}'.")
        return {}

def run_test_script(script_name, **kwargs):
    """
    Dynamically load and run a test script with optional arguments.

    Args:
        script_name (str): The name of the script inside the tests directory.
        kwargs: Arguments to pass to the test script.
    """
    root_dir = Path.Path(__file__).parent.parent.parent.parent  # Locate the project root
    test_dir = root_dir / "tests"
    script_path = test_dir / script_name

    if not script_path.exists():
        lgr.warning(f"Test script not found: {script_path}")
        return

    spec = importlib.util.spec_from_file_location(script_name, str(script_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[script_name] = module
    spec.loader.exec_module(module)

    if hasattr(module, "main"):
        module.main(**kwargs)  # Pass keyword arguments to the test script
    else:
        lgr.error(f"Test script {script_name} does not have a 'main' function.")

def update_env_with_config(config):
    """
    Updates environment variables from configuration.

    Args:
        config: Configuration dictionary
    """
    # Extract values from config with defaults
    db_path = config.get("db_path", "~/Desktop/worklist.db")
    db_echo = str(config.get("db_echo", "False"))
    users_db_path = config.get("users_db_path")

    # Expand the db_path from the config
    try:
        db_path_expanded = os.path.expanduser(db_path)
    except AttributeError:
        lgr.error("Invalid db_path in config.")
        return

    # Set environment variables directly (for API server)
    os.environ["DB_PATH"] = db_path_expanded
    os.environ["DB_ECHO"] = db_echo

    # Set users database path if provided in config
    if users_db_path:
        try:
            users_db_path_expanded = os.path.expanduser(users_db_path)
            os.environ["USERS_DB_PATH"] = users_db_path_expanded
            lgr.debug(f"USERS_DB_PATH set to {users_db_path_expanded}")
        except AttributeError:
            lgr.error("Invalid users_db_path in config.")

    # Set CORS configuration if provided
    api_config = config.get("api", {})
    if "cors_allowed_origins" in api_config:
        import json
        os.environ["CORS_ALLOWED_ORIGINS"] = json.dumps(api_config["cors_allowed_origins"])
        lgr.debug(f"CORS origins set to {api_config['cors_allowed_origins']}")

    if "cors_allow_credentials" in api_config:
        os.environ["CORS_ALLOW_CREDENTIALS"] = str(api_config["cors_allow_credentials"])

    if "cors_allow_methods" in api_config:
        import json
        os.environ["CORS_ALLOW_METHODS"] = json.dumps(api_config["cors_allow_methods"])

    if "cors_allow_headers" in api_config:
        import json
        os.environ["CORS_ALLOW_HEADERS"] = json.dumps(api_config["cors_allow_headers"])

    lgr.debug(f"Environment configured: DB_PATH={db_path_expanded}, DB_ECHO={db_echo}")

def main() -> None:
    args = parse_args()

    DEBUG = bool(os.environ.get("DEBUG", False))

    # Make sure to call this ONCE, before any SQLAlchemy imports that log
    setup_logging(debug=DEBUG)

    print("root logger level:", logging.getLogger().getEffectiveLevel())
    print("sqlalchemy logger level:", logging.getLogger("sqlalchemy").getEffectiveLevel())
    print("mwl_server logger level:", logging.getLogger("pylantir.mwl_server").getEffectiveLevel())
    print("pynetdicom logger level:", logging.getLogger("pynetdicom").getEffectiveLevel())



    if (args.command == "start"):
        # Load configuration (either user-specified or default)
        config = load_config(args.pylantir_config)
        # Load configuration into environment variables
        update_env_with_config(config)

        from ..mwl_server import run_mwl_server

        # Extract allowed AE Titles (default to empty list if missing)
        allowed_aet = config.get("allowed_aet", [])

        # Check if using new data_sources format or legacy format
        if "data_sources" in config:
            # NEW: Multi-source orchestration using plugin architecture
            lgr.info("Using new data_sources configuration format")

            from ..data_sources import get_plugin
            from ..data_sources.base import PluginError
            from ..redcap_to_db import STOP_EVENT
            import threading

            data_sources = config.get("data_sources", [])
            enabled_sources = [src for src in data_sources if src.get("enabled", True)]

            if not enabled_sources:
                lgr.warning("No enabled data sources found in configuration")
            else:
                lgr.info(f"Found {len(enabled_sources)} enabled data source(s)")

            def sync_data_source_repeatedly(source_config):
                """
                Generic sync loop for any data source plugin.

                This function works with any plugin type (REDCap, CSV, API, etc.)
                by using the plugin interface rather than source-specific code.
                """
                source_name = source_config.get("name", "unknown")
                source_type = source_config.get("type", "unknown")

                try:
                    # Get and instantiate the plugin
                    PluginClass = get_plugin(source_type)
                    lgr.info(f"[{source_name}] Initializing {source_type} plugin")

                    plugin = PluginClass()

                    # Validate plugin configuration
                    plugin_config = dict(source_config.get("config", {}))
                    if "field_mapping" in source_config:
                        plugin_config["field_mapping"] = source_config.get("field_mapping")
                    if "window_mode" in source_config:
                        plugin_config["window_mode"] = source_config.get("window_mode")
                    if "daily_window" in source_config:
                        plugin_config["daily_window"] = source_config.get("daily_window")

                    is_valid, error_msg = plugin.validate_config(plugin_config)
                    if not is_valid:
                        lgr.error(f"[{source_name}] Configuration validation failed: {error_msg}")
                        return

                    # Extract sync settings
                    sync_interval = source_config.get("sync_interval", 60)
                    operation_interval = source_config.get("operation_interval", {
                        "start_time": [0, 0],
                        "end_time": [23, 59]
                    })

                    lgr.info(f"[{source_name}] Starting sync loop (interval: {sync_interval}s)")

                    # Import database and sync utilities
                    from ..db_setup import Session
                    from ..models import WorklistItem
                    from ..redcap_to_db import generate_instance_uid, cleanup_memory_and_connections
                    from datetime import datetime, time as dt_time, timedelta
                    import logging

                    # Parse operation interval
                    start_h, start_m = operation_interval.get("start_time", [0, 0])
                    end_h, end_m = operation_interval.get("end_time", [23, 59])
                    start_time = dt_time(start_h, start_m)
                    end_time = dt_time(end_h, end_m)

                    last_sync_date = datetime.now().date() - timedelta(days=1)
                    interval_sync = sync_interval + 300  # Overlap to avoid missing data

                    # Sync loop
                    while not STOP_EVENT.is_set():
                        is_first_run = False
                        extended_interval = sync_interval

                        now_dt = datetime.now().replace(second=0, microsecond=0)
                        now_time = now_dt.time()
                        today_date = now_dt.date()

                        # Only sync within operation interval
                        if start_time <= now_time <= end_time:
                            is_first_run = (last_sync_date != today_date)

                            if is_first_run and (last_sync_date is not None):
                                yesterday = last_sync_date
                                dt_end_yesterday = datetime.combine(yesterday, end_time)
                                dt_start_today = datetime.combine(today_date, start_time)
                                delta = dt_start_today - dt_end_yesterday
                                extended_interval = delta.total_seconds()
                                # temporary increase interval to cover gap since last sync
                                # extended_interval += 6000000
                                logging.info(f"[{source_name}] First sync of the day at {now_time}")

                            # Fetch entries using plugin
                            try:
                                fetch_interval = extended_interval if is_first_run else interval_sync
                                field_mapping = source_config.get("field_mapping", {})

                                lgr.debug(f"[{source_name}] Fetching entries (interval: {fetch_interval}s)")
                                entries = plugin.fetch_entries(
                                    field_mapping=field_mapping,
                                    interval=fetch_interval
                                )

                                if entries:
                                    lgr.info(f"[{source_name}] Fetched {len(entries)} entries")

                                    # Get source-specific config
                                    site_id = source_config.get("config", {}).get("site_id")
                                    protocol = config.get("protocol", {})

                                    # Process entries (source-agnostic)
                                    session = Session()
                                    try:
                                        def _format_date(value):
                                            if value is None:
                                                return None
                                            if hasattr(value, "strftime"):
                                                return value.strftime("%Y-%m-%d")
                                            value_str = str(value).strip()
                                            if "-" in value_str and len(value_str) >= 10:
                                                return value_str[:10]
                                            if len(value_str) == 8 and value_str.isdigit():
                                                return f"{value_str[0:4]}-{value_str[4:6]}-{value_str[6:8]}"
                                            return value_str

                                        def _format_time(value):
                                            if value is None:
                                                return None
                                            if hasattr(value, "strftime"):
                                                return value.strftime("%H:%M")
                                            value_str = str(value).strip()
                                            if ":" in value_str:
                                                parts = value_str.split(":")
                                                if len(parts) >= 2:
                                                    hh = parts[0].zfill(2)
                                                    mm = parts[1].zfill(2)
                                                    return f"{hh}:{mm}"
                                            if len(value_str) == 6 and value_str.isdigit():
                                                return f"{value_str[0:2]}:{value_str[2:4]}"
                                            if len(value_str) == 4 and value_str.isdigit():
                                                return f"{value_str[0:2]}:{value_str[2:4]}"
                                            return value_str

                                        for record in entries:
                                            patient_id = record.get("patient_id")
                                            lgr.info(f"[{source_name}] Processing record for patient_id: {patient_id}")
                                            if not patient_id:
                                                lgr.info(f"[{source_name}] Skipping record with missing patient_id")
                                                continue

                                            existing_entry = session.query(WorklistItem).filter_by(patient_id=patient_id).first()

                                            scheduled_start_date = _format_date(record.get("scheduled_start_date"))
                                            scheduled_start_time = _format_time(record.get("scheduled_start_time"))

                                            if existing_entry:
                                                existing_entry.data_source = record.get("data_source") or source_name
                                                existing_entry.scheduled_start_date = scheduled_start_date
                                                existing_entry.scheduled_start_time = scheduled_start_time
                                            else:
                                                new_entry = WorklistItem(
                                                    study_instance_uid=record.get("study_instance_uid") or generate_instance_uid(),
                                                    patient_name=record.get("patient_name"),
                                                    patient_id=patient_id,
                                                    patient_birth_date=record.get("patient_birth_date"),
                                                    patient_sex=record.get("patient_sex"),
                                                    patient_weight_lb=record.get("patient_weight_lb"),
                                                    accession_number=record.get("accession_number"),
                                                    referring_physician_name=record.get("referring_physician_name"),
                                                    modality=record.get("modality", "MR"),
                                                    study_description=record.get("study_description"),
                                                    scheduled_station_aetitle=record.get("scheduled_station_aetitle"),
                                                    scheduled_start_date=scheduled_start_date,
                                                    scheduled_start_time=scheduled_start_time,
                                                    performing_physician=record.get("performing_physician"),
                                                    procedure_description=record.get("procedure_description"),
                                                    protocol_name=record.get("protocol_name") or protocol.get(site_id, "DEFAULT_PROTOCOL"),
                                                    station_name=record.get("station_name"),
                                                    hisris_coding_designator=record.get("hisris_coding_designator"),
                                                    performed_procedure_step_status=record.get(
                                                        "performed_procedure_step_status"
                                                    ) or "SCHEDULED",
                                                    data_source=record.get("data_source") or source_name
                                                )
                                                session.add(new_entry)

                                        session.commit()
                                        lgr.info(f"[{source_name}] Sync completed successfully")
                                    except Exception as e:
                                        session.rollback()
                                        lgr.error(f"[{source_name}] Database error: {e}")
                                    finally:
                                        session.expunge_all()
                                        session.close()
                                        cleanup_memory_and_connections()

                                last_sync_date = today_date

                            except Exception as e:
                                lgr.error(f"[{source_name}] Sync error: {e}")
                                import traceback
                                traceback.print_exc()

                        # Wait before next iteration
                        STOP_EVENT.wait(sync_interval)

                    lgr.info(f"[{source_name}] Exiting sync loop (STOP_EVENT set)")

                except PluginError as e:
                    lgr.error(f"[{source_name}] Plugin error: {e}")
                except Exception as e:
                    lgr.error(f"[{source_name}] Unexpected error: {e}")
                    import traceback
                    traceback.print_exc()

            # Start a thread for each enabled data source
            max_workers = len(enabled_sources) + 1  # +1 for MWL server
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit sync tasks for each data source
                for source in enabled_sources:
                    source_name = source.get("name", "unknown")
                    lgr.info(f"Starting background sync for data source: {source_name}")
                    executor.submit(sync_data_source_repeatedly, source)

                # Start the MWL server in the main thread
                run_mwl_server(
                    host=args.ip,
                    port=args.port,
                    aetitle=args.AEtitle,
                    allowed_aets=allowed_aet,
                )

        else:
            # LEGACY: Fall back to old single-source configuration
            lgr.warning("Using legacy configuration format. Consider migrating to data_sources format.")

            from ..redcap_to_db import sync_redcap_to_db_repeatedly

            # Extract the database update interval (default to 60 seconds if missing)
            db_update_interval = config.get("db_update_interval", 60)

            # Extract the operation interval (default from 00:00 to 23:59 hours if missing)
            operation_interval = config.get("operation_interval", {"start_time": [0,0], "end_time": [23,59]})

            # Extract the site id
            site = config.get("site", None)

            # Extract the redcap to worklist mapping
            redcap2wl = config.get("redcap2wl", {})

            # Extract protocol mapping
            protocol = config.get("protocol", {})

            # Create and update the MWL database
            with ThreadPoolExecutor(max_workers=2) as executor:
                future = executor.submit(
                    sync_redcap_to_db_repeatedly,
                    site_id=site,
                    protocol=protocol,
                    redcap2wl=redcap2wl,
                    interval=db_update_interval,
                    operation_interval=operation_interval,
                )

                run_mwl_server(
                    host=args.ip,
                    port=args.port,
                    aetitle=args.AEtitle,
                    allowed_aets=allowed_aet,
                )

    if (args.command == "query-db"):
        from ..mwl_server import run_mwl_server
        from ..redcap_to_db import sync_redcap_to_db_repeatedly
        lgr.info("Querying the MWL database")

        run_test_script(
            "query_db.py")

    if (args.command == "test-client"):
        from ..mwl_server import run_mwl_server
        from ..redcap_to_db import sync_redcap_to_db_repeatedly
        lgr.info("Running client test for MWL")
        # Run client.py to ensure that the worklist server is running and accepting connections
        run_test_script(
        "client.py",
        ip=args.ip,
        port=args.port,
        AEtitle=args.AEtitle,
        )

    if (args.command == "test-mpps"):
        from ..mwl_server import run_mwl_server
        from ..redcap_to_db import sync_redcap_to_db_repeatedly
        lgr.info("Running MPPS test")
        # Run MPPS tester with relevant arguments
        run_test_script(
            "mpps_tester.py",
            host=args.ip,
            port=args.port,
            calling_aet=args.callingAEtitle,
            called_aet=args.AEtitle,
            action=args.mpps_action,
            status=args.mpps_status,
            study_uid=args.study_uid,
            sop_instance_uid=args.sop_uid,
        )

    if (args.command == "start-api"):
        lgr.info("Starting Pylantir FastAPI server")
        try:
            # Check if API dependencies are available
            import uvicorn

            # Load configuration for database setup
            config = load_config(args.pylantir_config)
            update_env_with_config(config)
            users_db_path = config.get("users_db_path")  # Optional users database path

            # Import API app after env vars are set (DB_PATH, DB_ECHO, etc.)
            from ..api_server import app
            from ..auth_db_setup import init_auth_database, create_initial_admin_user

            # Initialize authentication database with configured path
            init_auth_database(users_db_path)
            create_initial_admin_user(users_db_path)

            lgr.info(f"API server starting on {args.api_host}:{args.api_port}")
            lgr.info("API documentation available at /docs")
            lgr.info("Default admin credentials: username='admin', password='admin123'")
            lgr.warning("Change the admin password immediately using 'pylantir admin-password'")

            uvicorn.run(app, host=args.api_host, port=args.api_port)

        except ImportError:
            lgr.error("API dependencies not installed. Install with: pip install pylantir[api]")
            sys.exit(1)
        except Exception as e:
            lgr.error(f"Failed to start API server: {e}")
            sys.exit(1)

    if (args.command == "admin-password"):
        lgr.info("Changing admin password")
        try:
            from ..auth_db_setup import get_auth_db, init_auth_database
            from ..auth_models import User, UserRole
            from ..auth_utils import get_password_hash
            import getpass

            # Load configuration to get users_db_path if available
            config = load_config(args.pylantir_config) if hasattr(args, 'pylantir_config') and args.pylantir_config else {}
            users_db_path = config.get("users_db_path")

            # Initialize database
            init_auth_database(users_db_path)

            # Get current password
            current_password = getpass.getpass("Enter current admin password: ")

            # Get new password
            new_password = getpass.getpass("Enter new password: ")
            confirm_password = getpass.getpass("Confirm new password: ")

            if new_password != confirm_password:
                lgr.error("Passwords do not match")
                sys.exit(1)

            if len(new_password) < 8:
                lgr.error("Password must be at least 8 characters long")
                sys.exit(1)

            # Update password in database
            db = next(get_auth_db())
            admin_user = db.query(User).filter(
                User.username == (args.username or "admin")
            ).first()

            if not admin_user:
                lgr.error("Admin user not found")
                sys.exit(1)

            from ..auth_utils import verify_password
            if not verify_password(current_password, admin_user.hashed_password):
                lgr.error("Current password is incorrect")
                sys.exit(1)

            # Update password
            admin_user.hashed_password = get_password_hash(new_password)
            db.commit()

            lgr.info("Admin password updated successfully")

        except ImportError:
            lgr.error("API dependencies not installed. Install with: pip install pylantir[api]")
            sys.exit(1)
        except Exception as e:
            lgr.error(f"Failed to change admin password: {e}")
            sys.exit(1)

    if (args.command == "create-user"):
        lgr.info("Creating new user")
        try:
            from ..auth_db_setup import get_auth_db, init_auth_database
            from ..auth_models import User, UserRole
            from ..auth_utils import get_password_hash
            import getpass

            # Load configuration to get users_db_path if available
            config = load_config(args.pylantir_config) if hasattr(args, 'pylantir_config') and args.pylantir_config else {}
            users_db_path = config.get("users_db_path")

            # Initialize database
            init_auth_database(users_db_path)

            # Get admin credentials
            admin_username = input("Enter admin username: ") or "admin"
            admin_password = getpass.getpass("Enter admin password: ")

            # Get new user details
            username = args.username or input("Enter new username: ")
            email = args.email or input("Enter email (optional): ") or None
            full_name = args.full_name or input("Enter full name (optional): ") or None
            password = args.password or getpass.getpass("Enter password for new user: ")

            # Get user role with interactive prompt
            if args.role == "read":  # Default value, prompt for role
                print("\nAvailable user roles:")
                print("  admin - Full administrative access")
                print("  write - Can create, read, update, and delete records")
                print("  read  - Read-only access (default)")
                role_input = input("Enter user role (admin/write/read) [read]: ").lower().strip()
                if role_input in ["admin", "write", "read"]:
                    role = role_input
                elif role_input == "":
                    role = "read"  # Keep default
                else:
                    lgr.error(f"Invalid role '{role_input}'. Valid roles are: admin, write, read")
                    sys.exit(1)
            else:
                role = args.role

            if not username or not password:
                lgr.error("Username and password are required")
                sys.exit(1)

            # Verify admin credentials
            db = next(get_auth_db())
            from ..auth_utils import authenticate_user
            admin_user = authenticate_user(db, admin_username, admin_password)

            if not admin_user or admin_user.role != UserRole.ADMIN:
                lgr.error("Invalid admin credentials or insufficient permissions")
                sys.exit(1)

            # Check if username already exists
            existing_user = db.query(User).filter(User.username == username).first()
            if existing_user:
                lgr.error(f"Username '{username}' already exists")
                sys.exit(1)

            # Create new user
            from datetime import datetime
            new_user = User(
                username=username,
                email=email,
                full_name=full_name,
                hashed_password=get_password_hash(password),
                role=UserRole(role),
                is_active=True,
                created_at=datetime.utcnow(),
                created_by=admin_user.id
            )

            db.add(new_user)
            db.commit()

            lgr.info(f"User '{username}' created successfully with role '{role}'")

        except ImportError:
            lgr.error("API dependencies not installed. Install with: pip install pylantir[api]")
            sys.exit(1)
        except Exception as e:
            lgr.error(f"Failed to create user: {e}")
            sys.exit(1)

    if (args.command == "list-users"):
        lgr.info("Listing all users")
        try:
            from ..auth_db_setup import get_auth_db, init_auth_database
            from ..auth_models import User, UserRole
            import getpass

            # Load configuration to get users_db_path if available
            config = load_config(args.pylantir_config) if hasattr(args, 'pylantir_config') and args.pylantir_config else {}
            users_db_path = config.get("users_db_path")

            # Initialize database
            init_auth_database(users_db_path)

            # Get admin credentials
            admin_username = input("Enter admin username: ") or "admin"
            admin_password = getpass.getpass("Enter admin password: ")

            # Verify admin credentials
            db = next(get_auth_db())
            from ..auth_utils import authenticate_user
            admin_user = authenticate_user(db, admin_username, admin_password)

            if not admin_user or admin_user.role != UserRole.ADMIN:
                lgr.error("Invalid admin credentials or insufficient permissions")
                sys.exit(1)

            # List all users
            users = db.query(User).all()

            print("\nUsers:")
            print("=" * 80)
            print(f"{'ID':<5} {'Username':<20} {'Role':<10} {'Active':<8} {'Email':<25} {'Last Login'}")
            print("-" * 80)

            for user in users:
                last_login = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "Never"
                print(f"{user.id:<5} {user.username:<20} {user.role.value:<10} {user.is_active:<8} {user.email or 'N/A':<25} {last_login}")

            print(f"\nTotal users: {len(users)}")

        except ImportError:
            lgr.error("API dependencies not installed. Install with: pip install pylantir[api]")
            sys.exit(1)
        except Exception as e:
            lgr.error(f"Failed to list users: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
