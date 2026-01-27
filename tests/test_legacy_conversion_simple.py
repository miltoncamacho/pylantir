"""
Simple validation test for legacy config auto-conversion logic.

This test validates the conversion logic without requiring the full
Pylantir environment to be installed.
"""

import json
import sys
from pathlib import Path


def convert_legacy_config(config):
    """
    Replicate the auto-conversion logic from cli/run.py load_config().

    This is a standalone copy for testing purposes.
    """
    import logging
    lgr = logging.getLogger(__name__)

    # Check if this is a legacy config (has redcap2wl but not data_sources)
    if "redcap2wl" in config and "data_sources" not in config:
        lgr.warning(
            "DEPRECATION: Legacy configuration format detected (redcap2wl). "
            "This format is deprecated and will be removed in a future version. "
            "Auto-converting to new data_sources format. "
            "See docs/quickstart.md for migration guide."
        )

        # Extract legacy fields
        site_id = config.get("site", "default")
        protocol_mapping = config.get("protocol", {})
        protocol = protocol_mapping.get(site_id, "DEFAULT_PROTOCOL")
        sync_interval = config.get("db_update_interval", 60)
        operation_interval = config.get("operation_interval", {
            "start_time": [0, 0],
            "end_time": [23, 59]
        })

        # Build new data_sources array
        data_source = {
            "name": "legacy_redcap",
            "type": "redcap",
            "enabled": True,
            "sync_interval": sync_interval,
            "operation_interval": operation_interval,
            "config": {
                "site_id": site_id,
                "protocol": protocol,
            },
            "field_mapping": config["redcap2wl"]
        }

        # Add data_sources to config
        config["data_sources"] = [data_source]

        lgr.info(f"Auto-converted legacy config to data_sources format with source '{data_source['name']}'")

    return config


def test_legacy_conversion():
    """Test that legacy config is properly converted."""

    print("\n=== Test 1: Legacy Config Auto-Conversion ===")

    legacy_config = {
        "db_path": "/tmp/test.db",
        "db_echo": "0",
        "db_update_interval": 120,
        "site": "792",
        "redcap2wl": {
            "study_id": "study_id",
            "family_id": "family_id",
            "demo_sex": "demo_sex"
        },
        "protocol": {
            "792": "BRAIN_MRI_3T",
            "other": "OTHER_PROTOCOL"
        },
        "operation_interval": {
            "start_time": [8, 0],
            "end_time": [18, 0]
        }
    }

    print("Original legacy config:")
    print(json.dumps(legacy_config, indent=2))

    # Convert
    converted = convert_legacy_config(legacy_config.copy())

    print("\nConverted config:")
    print(json.dumps(converted, indent=2))

    # Validate conversion
    assert "data_sources" in converted, "Should have data_sources"
    assert len(converted["data_sources"]) == 1, "Should have 1 data source"

    source = converted["data_sources"][0]
    assert source["name"] == "legacy_redcap", "Name should be legacy_redcap"
    assert source["type"] == "redcap", "Type should be redcap"
    assert source["enabled"] is True, "Should be enabled"
    assert source["sync_interval"] == 120, "Sync interval should match db_update_interval"
    assert source["config"]["site_id"] == "792", "site_id should match site"
    assert source["config"]["protocol"] == "BRAIN_MRI_3T", "protocol should match site protocol"
    assert source["field_mapping"] == legacy_config["redcap2wl"], "field_mapping should match redcap2wl"
    assert source["operation_interval"]["start_time"] == [8, 0], "start_time preserved"
    assert source["operation_interval"]["end_time"] == [18, 0], "end_time preserved"

    print("\n✅ Legacy conversion test PASSED")
    return True


def test_new_format_unchanged():
    """Test that new format configs are not modified."""

    print("\n=== Test 2: New Config Format (No Conversion) ===")

    new_config = {
        "db_path": "/tmp/test.db",
        "data_sources": [
            {
                "name": "my_redcap",
                "type": "redcap",
                "enabled": True,
                "sync_interval": 60,
                "config": {"site_id": "123", "protocol": "TEST"}
            }
        ]
    }

    print("New format config:")
    print(json.dumps(new_config, indent=2))

    # "Convert" (should be no-op)
    result = convert_legacy_config(new_config.copy())

    # Validate unchanged
    assert result == new_config, "New config should not be modified"
    assert result["data_sources"][0]["name"] == "my_redcap", "Name should be preserved"

    print("\n✅ New format preservation test PASSED")
    return True


def test_real_config_structure():
    """Test the actual mwl_config.json structure if it exists."""

    print("\n=== Test 3: Real Config File Validation ===")

    config_path = Path(__file__).parent.parent / "src" / "pylantir" / "config" / "mwl_config.json"

    if not config_path.exists():
        print(f"⚠️  Config file not found at {config_path}")
        print("Skipping real config test")
        return True

    print(f"Reading config from: {config_path}")

    with open(config_path) as f:
        real_config = json.load(f)

    # Check if it's legacy format
    if "redcap2wl" in real_config and "data_sources" not in real_config:
        print("✓ Detected legacy config format")
        print(f"  - Has redcap2wl: {bool('redcap2wl' in real_config)}")
        print(f"  - Has data_sources: {bool('data_sources' in real_config)}")
        print(f"  - Site: {real_config.get('site', 'N/A')}")
        print(f"  - Protocol: {real_config.get('protocol', {})}")

        # Convert
        converted = convert_legacy_config(real_config.copy())

        # Validate
        assert "data_sources" in converted, "Real config should be converted"
        print(f"✓ Converted to {len(converted['data_sources'])} data source(s)")

        source = converted["data_sources"][0]
        print(f"  - Source name: {source['name']}")
        print(f"  - Source type: {source['type']}")
        print(f"  - Site ID: {source['config']['site_id']}")
        print(f"  - Protocol: {source['config']['protocol']}")
        print(f"  - Field mappings: {len(source['field_mapping'])} fields")

    else:
        print("⚠️  Config is already in new format or invalid")
        print(f"  - Has redcap2wl: {bool('redcap2wl' in real_config)}")
        print(f"  - Has data_sources: {bool('data_sources' in real_config)}")

    print("\n✅ Real config validation test PASSED")
    return True


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    print("="*70)
    print("Legacy Config Auto-Conversion Validation")
    print("="*70)

    tests = [
        ("Legacy config conversion", test_legacy_conversion),
        ("New config preservation", test_new_format_unchanged),
        ("Real config structure", test_real_config_structure),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            print(f"\n{'='*70}")
            print(f"Running: {name}")
            print('='*70)
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n❌ FAILED: {name}")
        except Exception as e:
            failed += 1
            print(f"\n❌ FAILED: {name}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print(f"\n{'='*70}")
    print(f"Summary: {passed} passed, {failed} failed")
    print('='*70)

    sys.exit(0 if failed == 0 else 1)
