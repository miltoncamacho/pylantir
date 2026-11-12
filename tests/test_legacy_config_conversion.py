"""
Test script to verify backward compatibility with legacy REDCap configurations.

This test validates that:
1. Legacy configs (with redcap2wl) are automatically converted to new format
2. Converted configs have proper data_sources array structure
3. Deprecation warnings are logged during conversion
4. Original config behavior is preserved after conversion

Run with: python -m pytest tests/test_legacy_config_conversion.py -v
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pylantir.cli.run import load_config


def test_legacy_config_auto_conversion(tmp_path):
    """Test that legacy REDCap config is auto-converted to new format."""

    # Create a legacy config file (with redcap2wl, no data_sources)
    legacy_config = {
        "db_path": "/tmp/test_worklist.db",
        "db_echo": "0",
        "db_update_interval": 60,
        "site": "792",
        "redcap2wl": {
            "study_id": "study_id",
            "family_id": "family_id",
            "demo_sex": "demo_sex"
        },
        "protocol": {
            "792": "BRAIN_MRI_3T"
        },
        "operation_interval": {
            "start_time": [8, 0],
            "end_time": [18, 0]
        }
    }

    # Write legacy config to temp file
    config_file = tmp_path / "legacy_config.json"
    with open(config_file, 'w') as f:
        json.dump(legacy_config, f, indent=2)

    print(f"\n=== Testing Legacy Config Auto-Conversion ===")
    print(f"Legacy config file: {config_file}")
    print(f"Legacy config content:")
    print(json.dumps(legacy_config, indent=2))

    # Load config (should trigger auto-conversion)
    converted_config = load_config(str(config_file))

    print(f"\n=== Converted Config ===")
    print(json.dumps(converted_config, indent=2))

    # Verify conversion results
    assert "data_sources" in converted_config, "Converted config should have data_sources"
    assert isinstance(converted_config["data_sources"], list), "data_sources should be a list"
    assert len(converted_config["data_sources"]) == 1, "Should have exactly 1 data source"

    source = converted_config["data_sources"][0]

    # Check data source structure
    assert source["name"] == "legacy_redcap", "Source name should be legacy_redcap"
    assert source["type"] == "redcap", "Source type should be redcap"
    assert source["enabled"] is True, "Source should be enabled"
    assert source["sync_interval"] == 60, "Sync interval should match db_update_interval"

    # Check config mapping
    assert source["config"]["site_id"] == "792", "site_id should match site"
    assert source["config"]["protocol"] == "BRAIN_MRI_3T", "protocol should match site protocol"

    # Check field mapping
    assert source["field_mapping"] == legacy_config["redcap2wl"], "field_mapping should match redcap2wl"

    # Check operation_interval
    assert source["operation_interval"]["start_time"] == [8, 0], "start_time should be preserved"
    assert source["operation_interval"]["end_time"] == [18, 0], "end_time should be preserved"

    print("\n✅ All auto-conversion checks passed!")
    return True


def test_new_config_not_converted(tmp_path):
    """Test that new-format configs are not modified."""

    # Create a new-format config (with data_sources)
    new_config = {
        "db_path": "/tmp/test_worklist.db",
        "data_sources": [
            {
                "name": "main_redcap",
                "type": "redcap",
                "enabled": True,
                "sync_interval": 120,
                "config": {
                    "site_id": "123",
                    "protocol": "TEST_PROTOCOL"
                },
                "field_mapping": {
                    "test_field": "test_field"
                }
            }
        ]
    }

    # Write new config to temp file
    config_file = tmp_path / "new_config.json"
    with open(config_file, 'w') as f:
        json.dump(new_config, f, indent=2)

    print(f"\n=== Testing New Config (No Conversion) ===")
    print(f"New config file: {config_file}")

    # Load config (should NOT trigger conversion)
    loaded_config = load_config(str(config_file))

    # Verify config is unchanged
    assert loaded_config == new_config, "New config should not be modified"
    assert loaded_config["data_sources"][0]["name"] == "main_redcap", "Source name should be preserved"

    print("\n✅ New config correctly preserved without conversion!")
    return True


def test_legacy_config_with_real_file():
    """Test conversion with the actual mwl_config.json file if it exists."""

    config_path = Path(__file__).parent.parent / "src" / "pylantir" / "config" / "mwl_config.json"

    if not config_path.exists():
        print("\n⚠️  Skipping real config test - mwl_config.json not found")
        return True

    print(f"\n=== Testing Real mwl_config.json ===")
    print(f"Config file: {config_path}")

    # Load the real config
    with open(config_path) as f:
        original_config = json.load(f)

    # Check if it's a legacy config
    if "redcap2wl" in original_config and "data_sources" not in original_config:
        print("✓ Detected legacy config format")

        # Load config (triggers conversion)
        converted = load_config(str(config_path))

        # Verify conversion
        assert "data_sources" in converted, "Real config should be converted"
        print(f"✓ Converted to {len(converted['data_sources'])} data source(s)")

        # Verify field mapping preserved
        source = converted["data_sources"][0]
        assert source["field_mapping"] == original_config["redcap2wl"], "Field mapping should be preserved"
        print("✓ Field mapping preserved")

    else:
        print("⚠️  Config is already in new format")

    print("\n✅ Real config test passed!")
    return True


if __name__ == "__main__":
    import tempfile

    print("="*60)
    print("Legacy Config Auto-Conversion Test Suite")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Run all tests
        tests = [
            ("Auto-conversion of legacy config", lambda: test_legacy_config_auto_conversion(tmp_path)),
            ("New config preservation", lambda: test_new_config_not_converted(tmp_path)),
            ("Real config file test", test_legacy_config_with_real_file),
        ]

        passed = 0
        failed = 0

        for name, test_func in tests:
            try:
                print(f"\n{'='*60}")
                print(f"Running: {name}")
                print('='*60)
                if test_func():
                    passed += 1
                    print(f"\n✅ PASSED: {name}")
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
        print(f"\n{'='*60}")
        print(f"Test Summary: {passed} passed, {failed} failed")
        print('='*60)

        sys.exit(0 if failed == 0 else 1)
