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

from ..mwl_server import run_mwl_server
from ..redcap_to_db import sync_redcap_to_db


DEBUG = bool(os.environ.get("DEBUG", False))
coloredlogs.install()

if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    logging.root.setLevel(logging.DEBUG)
    root_handler = logging.root.handlers[0]
    root_handler.setFormatter(
        logging.Formatter("%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s")
    )
else:
    root_handler = logging.root.handlers[0]
    root_handler.setFormatter(
        logging.Formatter("%(levelname)-8s %(message)s")
    )
    logging.root.setLevel(logging.INFO)

lgr = logging.getLogger(__name__)

def parse_args():
    default_config_path = str(pkg_resources.files("pylantir").joinpath("config/mwl_config.json"))

    p = argparse.ArgumentParser(description="pylantir - Python DICOM Modality WorkList and Modality Performed Procedure Step compliance")
    p.add_argument("command",
                    help="""
                        Command to run:
                        - start: start the MWL server
                        - test-client: run tests for MWL
                        - test-mpps: run tests for MPPS
                    """,
                    choices=["start", "test-client", "test-mpps"],
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


def main() -> None:
    args = parse_args()

    # Load configuration (either user-specified or default)
    config = load_config(args.pylantir_config)

    # Extract allowed AE Titles (default to empty list if missing)
    allowed_aet = config.get("allowed_aet", [])

    # Extract mri_visit_session_mapping (default to empty list if missing)
    mri_visit_session_mapping = config.get("mri_visit_session_mapping", {})

    # Extract the site id
    site = config.get("site", None)

    # Extract the redcap to worklist mapping
    redcap2wl = config.get("redcap2wl", {})

    # EXtract protocol mapping
    protocol = config.get("protocol", {})

    if (args.command == "start"):
        sync_redcap_to_db(
            mri_visit_mapping=mri_visit_session_mapping,
            site_id=site,
            protocol=protocol,
            redcap2wl=redcap2wl,
        )

        run_mwl_server(
            host=args.ip,
            port=args.port,
            aetitle=args.AEtitle,
            allowed_aets=allowed_aet,
        )

    if (args.command == "test-client"):
        lgr.info("Running client test for MWL")

        # Run client.py to ensure that the worklist server is running and accepting connections
        run_test_script(
        "client.py",
        ip=args.ip,
        port=args.port,
        AEtitle=args.AEtitle,
        )

    if (args.command == "test-mpps"):
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
