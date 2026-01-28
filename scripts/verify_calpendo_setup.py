#!/usr/bin/env python3
"""
Verification script for Calpendo plugin setup.

Checks:
1. Environment variables (CALPENDO_USERNAME, CALPENDO_PASSWORD)
2. API connectivity to Calpendo server
3. Configuration file structure
4. Plugin registration in PLUGIN_REGISTRY
5. Required dependencies (requests, pytz)

Exit Codes:
- 0: All checks passed
- 1: One or more checks failed
"""

import os
import sys
import json
from pathlib import Path
from typing import Tuple

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text: str) -> None:
    """Print formatted section header."""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}\n")


def check_pass(message: str) -> None:
    """Print success message."""
    print(f"{GREEN}✓{RESET} {message}")


def check_fail(message: str) -> None:
    """Print failure message."""
    print(f"{RED}✗{RESET} {message}")


def check_warn(message: str) -> None:
    """Print warning message."""
    print(f"{YELLOW}⚠{RESET} {message}")


def check_environment_variables() -> bool:
    """Check if required environment variables are set."""
    print_header("1. Environment Variables Check")

    username = os.getenv("CALPENDO_USERNAME")
    password = os.getenv("CALPENDO_PASSWORD")

    passed = True

    if username:
        check_pass(f"CALPENDO_USERNAME is set (value: {username[:3]}***)")
    else:
        check_fail("CALPENDO_USERNAME is not set")
        print(f"   {YELLOW}Set with: export CALPENDO_USERNAME='your-username'{RESET}")
        passed = False

    if password:
        check_pass("CALPENDO_PASSWORD is set (hidden)")
    else:
        check_fail("CALPENDO_PASSWORD is not set")
        print(f"   {YELLOW}Set with: export CALPENDO_PASSWORD='your-password'{RESET}")
        passed = False

    return passed


def check_dependencies() -> bool:
    """Check if required Python packages are installed."""
    print_header("2. Dependency Check")

    passed = True
    required_packages = {
        "requests": "HTTP client for Calpendo API",
        "pytz": "Timezone handling (Mountain Time ↔ UTC)",
    }

    for package, description in required_packages.items():
        try:
            __import__(package)
            check_pass(f"{package} is installed ({description})")
        except ImportError:
            check_fail(f"{package} is not installed")
            print(f"   {YELLOW}Install with: pip install {package}{RESET}")
            passed = False

    return passed


def check_plugin_registration() -> bool:
    """Check if CalendoPlugin is registered in PLUGIN_REGISTRY."""
    print_header("3. Plugin Registration Check")

    try:
        # Add src to path to import plugin
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root / "src"))

        from pylantir.data_sources import PLUGIN_REGISTRY
        from pylantir.data_sources.calpendo_plugin import CalendoPlugin

        if "calpendo" in PLUGIN_REGISTRY:
            check_pass("'calpendo' found in PLUGIN_REGISTRY")

            if PLUGIN_REGISTRY["calpendo"] is CalendoPlugin:
                check_pass("CalendoPlugin class correctly registered")
                return True
            else:
                check_fail(f"'calpendo' registered as {PLUGIN_REGISTRY['calpendo']}, expected CalendoPlugin")
                return False
        else:
            check_fail("'calpendo' not found in PLUGIN_REGISTRY")
            available = ", ".join(PLUGIN_REGISTRY.keys())
            print(f"   {YELLOW}Available plugins: {available}{RESET}")
            return False

    except ImportError as e:
        check_fail(f"Failed to import plugin: {e}")
        return False
    except Exception as e:
        check_fail(f"Unexpected error checking registration: {e}")
        return False


def check_configuration_file(config_path: str) -> bool:
    """Validate configuration file structure."""
    print_header("4. Configuration File Check")

    path = Path(config_path)
    if not path.exists():
        check_warn(f"Configuration file not found: {config_path}")
        print(f"   {YELLOW}Example config: src/pylantir/config/calpendo_config_example.json{RESET}")
        return True  # Not a failure, just a warning

    try:
        with open(path, "r") as f:
            config = json.load(f)

        check_pass(f"Configuration file loaded: {config_path}")

        # Check for data_sources array
        if "data_sources" not in config:
            check_warn("No 'data_sources' array in config (Calpendo not configured)")
            return True

        # Find Calpendo data source
        calpendo_sources = [
            ds for ds in config["data_sources"]
            if ds.get("type") == "calpendo"
        ]

        if not calpendo_sources:
            check_warn("No Calpendo data source configured in 'data_sources' array")
            print(f"   {YELLOW}Add Calpendo config - see calpendo_config_example.json{RESET}")
            return True

        check_pass(f"Found {len(calpendo_sources)} Calpendo data source(s)")

        # Validate first Calpendo source structure
        source = calpendo_sources[0]
        required_fields = ["name", "type", "base_url", "resources", "field_mapping"]

        passed = True
        for field in required_fields:
            if field in source:
                check_pass(f"  Required field '{field}' present")
            else:
                check_fail(f"  Required field '{field}' missing")
                passed = False

        # Check resources is a list
        if isinstance(source.get("resources"), list):
            check_pass(f"  'resources' is a list with {len(source['resources'])} item(s)")
        else:
            check_fail("  'resources' should be a list")
            passed = False

        # Check field_mapping is a dict
        if isinstance(source.get("field_mapping"), dict):
            check_pass(f"  'field_mapping' is a dict with {len(source['field_mapping'])} field(s)")
        else:
            check_fail("  'field_mapping' should be a dict")
            passed = False

        return passed

    except json.JSONDecodeError as e:
        check_fail(f"Invalid JSON in configuration file: {e}")
        return False
    except Exception as e:
        check_fail(f"Error reading configuration: {e}")
        return False


def check_api_connectivity(config_path: str) -> Tuple[bool, str]:
    """Test connectivity to Calpendo API."""
    print_header("5. API Connectivity Check")

    username = os.getenv("CALPENDO_USERNAME")
    password = os.getenv("CALPENDO_PASSWORD")

    if not username or not password:
        check_warn("Skipping API connectivity test (credentials not set)")
        return True, "skipped"

    # Try to get base_url from config
    base_url = None
    path = Path(config_path)
    if path.exists():
        try:
            with open(path, "r") as f:
                config = json.load(f)

            calpendo_sources = [
                ds for ds in config.get("data_sources", [])
                if ds.get("type") == "calpendo"
            ]

            if calpendo_sources:
                base_url = calpendo_sources[0].get("base_url")
        except Exception:
            pass

    if not base_url:
        check_warn("No base_url found in config, skipping connectivity test")
        print(f"   {YELLOW}Configure base_url in your config file to test connectivity{RESET}")
        return True, "skipped"

    try:
        import requests

        # Test basic auth endpoint
        test_url = f"{base_url}/calendar/resources"
        check_pass(f"Testing connectivity to: {test_url}")

        response = requests.get(
            test_url,
            auth=(username, password),
            timeout=10
        )

        if response.status_code == 200:
            check_pass(f"API connectivity successful (HTTP 200)")
            check_pass(f"Response length: {len(response.text)} bytes")
            return True, "success"
        elif response.status_code == 401:
            check_fail("Authentication failed (HTTP 401)")
            print(f"   {YELLOW}Check your CALPENDO_USERNAME and CALPENDO_PASSWORD{RESET}")
            return False, "auth_failed"
        else:
            check_warn(f"Unexpected response code: {response.status_code}")
            return True, "unexpected_response"

    except ImportError:
        check_warn("'requests' library not installed, skipping connectivity test")
        return True, "skipped"
    except requests.exceptions.Timeout:
        check_fail("API request timed out (10 seconds)")
        print(f"   {YELLOW}Check if Calpendo server is accessible from this network{RESET}")
        return False, "timeout"
    except requests.exceptions.ConnectionError as e:
        check_fail(f"Connection error: {e}")
        print(f"   {YELLOW}Check base_url and network connectivity{RESET}")
        return False, "connection_error"
    except Exception as e:
        check_fail(f"Unexpected error testing API: {e}")
        return False, "error"


def main() -> int:
    """Run all verification checks."""
    print(f"\n{BLUE}{'=' * 70}{RESET}")
    print(f"{BLUE}Calpendo Plugin Setup Verification{RESET}")
    print(f"{BLUE}{'=' * 70}{RESET}")

    # Determine config path
    project_root = Path(__file__).parent.parent
    config_path = project_root / "src" / "pylantir" / "config" / "mwl_config.json"

    # Run all checks
    checks = {
        "Environment Variables": check_environment_variables(),
        "Dependencies": check_dependencies(),
        "Plugin Registration": check_plugin_registration(),
        "Configuration File": check_configuration_file(str(config_path)),
    }

    # API connectivity returns (passed, status)
    api_result, api_status = check_api_connectivity(str(config_path))
    checks["API Connectivity"] = api_result

    # Summary
    print_header("Verification Summary")

    passed_count = sum(1 for v in checks.values() if v)
    total_count = len(checks)

    for check_name, passed in checks.items():
        if passed:
            check_pass(f"{check_name}: PASSED")
        else:
            check_fail(f"{check_name}: FAILED")

    print(f"\n{BLUE}{'=' * 70}{RESET}")

    if passed_count == total_count:
        print(f"{GREEN}✓ All checks passed ({passed_count}/{total_count}){RESET}")

        if api_status == "skipped":
            print(f"\n{YELLOW}Note: API connectivity test was skipped.{RESET}")
            print(f"{YELLOW}To test API connectivity, configure a Calpendo data source{RESET}")
            print(f"{YELLOW}in your mwl_config.json and set environment variables.{RESET}")

        print(f"\n{GREEN}✓ Calpendo plugin is ready to use!{RESET}")
        return 0
    else:
        failed_count = total_count - passed_count
        print(f"{RED}✗ {failed_count} check(s) failed ({passed_count}/{total_count} passed){RESET}")
        print(f"\n{YELLOW}Fix the failed checks above before using the Calpendo plugin.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
