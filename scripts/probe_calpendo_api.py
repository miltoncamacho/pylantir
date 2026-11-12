#!/usr/bin/env python3
"""Probe Calpendo list/detail endpoints without running the worklist sync."""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

import requests


def describe(response: requests.Response) -> None:
    history = " -> ".join(str(item.status_code) for item in response.history)
    print(f"  HTTP: {response.status_code}")
    print(f"  Content-Type: {response.headers.get('Content-Type', '<missing>')}")
    print(f"  Final URL: {response.url}")
    if history:
        print(f"  Redirects: {history} -> {response.status_code}")


def get_json(session: requests.Session, url: str, timeout: float) -> Optional[dict]:
    response = session.get(url, timeout=timeout)
    describe(response)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        print(f"  HTTP error: {exc}")
        return None
    try:
        value = response.json()
    except requests.exceptions.JSONDecodeError:
        preview = " ".join((response.text or "")[:300].split()) or "<empty body>"
        print(f"  Not JSON. Body preview: {preview!r}")
        return None
    if not isinstance(value, dict):
        print(f"  Unexpected JSON root: {type(value).__name__}")
        return None
    return value


def field_paths(value: object, prefix: str = "") -> list[str]:
    if not isinstance(value, dict):
        return []
    paths = []
    for key, child in sorted(value.items()):
        path = f"{prefix}.{key}" if prefix else key
        paths.append(path)
        paths.extend(field_paths(child, path))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("CALPENDO_API_URL"))
    parser.add_argument("--resource", help="Exact Calpendo resource name")
    parser.add_argument("--booking-id", type=int, help="Skip discovery and inspect this booking")
    parser.add_argument("--days", type=int, default=14, help="Days before/after today to query")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--legacy", action="store_true", help="Probe legacy /webdav endpoints")
    args = parser.parse_args()

    username = os.getenv("CALPENDO_USERNAME")
    password = os.getenv("CALPENDO_PASSWORD")
    if not args.base_url or not username or not password:
        parser.error("set CALPENDO_USERNAME and CALPENDO_PASSWORD and pass --base-url (or set CALPENDO_API_URL)")

    root = "/webdav" if args.legacy else "/api"
    base = args.base_url.rstrip("/") + root
    session = requests.Session()
    session.auth = (username, password)
    session.headers.update({"Accept": "application/json", "User-Agent": "pylantir-calpendo-probe/1"})

    print(f"Probing {root} with JSON requested (credentials hidden)")
    print("\n1. REST API catalog")
    catalog = get_json(session, f"{base}/b", args.timeout)
    if catalog is None:
        return 1

    booking_id = args.booking_id
    if booking_id is None:
        now = datetime.now().astimezone()
        start = now - timedelta(days=args.days)
        end = now + timedelta(days=args.days)
        query = (
            f"AND/dateRange.start/GE/{start:%Y%m%d-%H%M}"
            f"/dateRange.start/LT/{end:%Y%m%d-%H%M}"
        )
        if args.resource:
            query += f"/OR/resource.name/EQ/{quote(args.resource)}"
        print("\n2. Booking query")
        listing = get_json(session, f"{base}/q/Calpendo.Booking/{query}", args.timeout)
        if listing is None:
            return 1
        biskits = listing.get("biskits", [])
        print(f"  Bookings returned: {len(biskits)}")
        if not biskits:
            print("  No booking is available to inspect; widen --days or check --resource.")
            return 2
        booking_id = biskits[0].get("id")
        if booking_id is None:
            print("  First query result has no id field.")
            return 1

    print(f"\n3. Booking detail ({booking_id})")
    detail = get_json(session, f"{base}/b/Calpendo.Booking/{booking_id}", args.timeout)
    if detail is None:
        return 1

    print("\n4. Exported field paths")
    paths = field_paths(detail)
    for path in paths:
        print(f"  {path}")

    expected = {
        "booking ID": ("id",),
        "patient/title source": ("title", "properties.title"),
        "booking status": ("status", "properties.status"),
        "schedule": ("formattedName", "properties.dateRange"),
        "study/project": ("properties.project.formattedName",),
        "scanner/resource": ("properties.resource.formattedName",),
    }
    print("\n5. Worklist field availability")
    available = set(paths)
    for label, alternatives in expected.items():
        found = next((path for path in alternatives if path in available), None)
        detail_text = found or " or ".join(alternatives)
        print(f"  {'YES' if found else 'NO ':3} {label}: {detail_text}")

    if os.getenv("CALPENDO_PROBE_DUMP_JSON") == "1":
        print("\nRaw booking JSON (may contain sensitive data):")
        print(json.dumps(detail, indent=2, sort_keys=True))
    else:
        print("\nRaw values suppressed. Set CALPENDO_PROBE_DUMP_JSON=1 only if safe to display PHI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
