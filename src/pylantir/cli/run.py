from __future__ import annotations

import argparse
import logging
import os
import json
import importlib.resources as pkg_resources
import pathlib as Path
import coloredlogs

from ..mwl_server import run_mwl_server
from ..populate_db import populate_data

#TODO add tests

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

    p = argparse.ArgumentParser(description="pylantir - Python Modality WorkList and Modality Performed Procedure Step compliance")
    p.add_argument("command", help="start or test")
    p.add_argument("--AE", help="AE Title for the server")
    p.add_argument("--ip", help="IP/host address for the server", default="0.0.0.0")
    p.add_argument("--port", type=int, help="port for the server", default=4242)

    p.add_argument(
        "--pylantir_config",
        help="""
            Path to the configuration JSON file containing pylantir configs:
            - allowed_aet: list of allowed AE titles e.g. ["MRI_SCANNER", "MRI_SCANNER_2"]
        """, #TODO: allow more usages
        default=None,
    )

    p.add_argument(
        "--create-mpps",
        action="store_true",
        default=False,
        help="Create a MPPS instance and send in progress status",
    )

    p.add_argument(
        "--set-mpps",
        action="store_true",
        default=False,
        help="Set the status to completed or discontinued",
    )

    p.add_argument(
        "--status",
        default=None,
        type=str,
        choices=["COMPLETED", "DISCONTINUED"],
        help="Status to set for MPPS either COMPLETED or DISCONTINUED",
    )

    p.add_argument(
        "--study-uid",
        default=None,
        type=str,
        help="StudyInstanceUID to test MPPS",
    )

    p.add_argument(
        "--sop-uid",
        default=None,
        type=str,
        help="SOPInstanceUID to test MPPS",

    return p.parse_args()

def load_config(config_path=None):
    """
    Load configuration file, either from a user-provided path or the default package location.

    Args:
        config_path (str | Path, optional): Path to the configuration JSON file.

    Returns:
        dict: Parsed JSON config as a dictionary.
    """
    # If no custom config is provided, use the default package config
    if config_path is None:
        config_path = pkg_resources.files("pylantir").joinpath("config/mwl_config.json")

    config_path = Path(config_path)  # Ensure it's a Path object

    try:
        # Load configuration file
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


def main() -> None:
    args = parse_args()

    # Load configuration (either user-specified or default)
    config = load_config(args.pylantir_config)

    # Extract allowed AE Titles (default to empty list if missing)
    allowed_aet = config.get("allowed_aet", [])

    if args.command == "start":
        populate_data()

        run_mwl_server(
            host=args.ip,
            port=args.port,
            aetitle=args.AE,
            allowed_aets=args.allowed_aet,
        )


if __name__ == "__main__":
    main()