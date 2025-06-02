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
                        - query: query the MWL db
                        - test-client: run tests for MWL
                        - test-mpps: run tests for MPPS
                    """,
                    choices=["start", "query-db", "test-client", "test-mpps"],
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

def update_env_with_config(db_path="~/Desktop/worklist.db", db_echo="False", env_path=".env"):
    """
    Updates db_path from the config to DB_PATH in .env.
    """

    # Expand the db_path from the config
    try:
        db_path_expanded = os.path.expanduser(db_path)
    except AttributeError:
        lgr.error("Invalid db_path in config.")
        return

    # Set the default env_path to the src/pylantir folder
    dot_env_path = pkg_resources.files("pylantir").joinpath(env_path)
    dot_env_path = Path.Path(dot_env_path)

    # Write to .env using python-dotenv's set_key
    set_key(dot_env_path, "DB_PATH", db_path_expanded)
    set_key(dot_env_path, "DB_ECHO", db_echo)

    lgr.debug(f"DB_PATH set to {db_path_expanded} and DB_ECHO to {db_echo} in {dot_env_path}")

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
        # Extract the database path (default to worklist.db if missing) &
        # Extract the database echo setting (default to False if missing)
        db_path = config.get("db_path", "./worklist.db")
        db_echo = config.get("db_echo", "False")
        update_env_with_config(db_path=db_path, db_echo=db_echo)


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


if __name__ == "__main__":
    main()
