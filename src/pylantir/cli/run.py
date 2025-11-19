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
        from ..redcap_to_db import sync_redcap_to_db_repeatedly

        # Extract the database update interval (default to 60 seconds if missing)
        db_update_interval = config.get("db_update_interval", 60)

        # Extract the operation interval (default from 00:00 to 23:59 hours if missing)
        operation_interval = config.get("operation_interval", {"start_time": [0,0], "end_time": [23,59]})

        # Extract allowed AE Titles (default to empty list if missing)
        allowed_aet = config.get("allowed_aet", [])

        # Extract the site id
        site = config.get("site", None)

        # Extract the redcap to worklist mapping
        redcap2wl = config.get("redcap2wl", {})

        # EXtract protocol mapping
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

                # sync_redcap_to_db(
                #     mri_visit_mapping=mri_visit_session_mapping,
                #     site_id=site,
                #     protocol=protocol,
                #     redcap2wl=redcap2wl,
                # )

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
            from ..api_server import app
            from ..auth_db_setup import init_auth_database, create_initial_admin_user

            # Load configuration for database setup
            config = load_config(args.pylantir_config)
            update_env_with_config(config)
            users_db_path = config.get("users_db_path")  # Optional users database path

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
