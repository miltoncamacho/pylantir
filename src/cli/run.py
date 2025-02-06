from __future__ import annotations

import argparse
import logging
import os

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

    p = argparse.ArgumentParser(description="forbids - setup and validate protocol compliance")
    p.add_argument("command", help="start or test")
    p.add_argument("--AE", help="AE Title for the server")
    p.add_argument("--ip", help="IP/host address for the server", default="0.0.0.0")
    p.add_argument("--port", type=int, help="port for the server", default=4242)
    p.add_argument("--config", help="path to the configuration json file containing allowed AE titles")
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

    p.add_argument(
        "--status",
        default=None,
        type=str,
        help="Status to set for MPPS either COMPLETED or DISCONTINUED",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "start":
        populate_data()
        run_mwl_server(
            host=args.ip,
            port=args.port,
            aetitle=args.AE,
        )


if __name__ == "__main__":
    main()