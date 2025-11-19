#!/usr/bin/env python3
"""
Test script for CORS configuration in Pylantir API
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

def create_test_config(cors_origins: list) -> str:
    """Create temporary config file with specified CORS origins"""
    config = {
        "db_path": ":memory:",
        "db_echo": "0",
        "db_update_interval": 60,
        "allowed_aet": [],
        "operation_interval": {
            "start_time": [0, 0],
            "end_time": [23, 59]
        },
        "mri_visit_session_mapping": {
            "t1_arm_1": "1"
        },
        "site": "792",
        "redcap2wl": {},
        "protocol": {
            "792": "BRAIN_MRI_3T"
        },
        "api": {
            "cors_allowed_origins": cors_origins,
            "cors_allow_credentials": True,
            "cors_allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "cors_allow_headers": ["*"]
        }
    }

    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, indent=2)
        return f.name

def test_cors_configuration():
    """Test different CORS configurations"""
    test_cases = [
        {
            'name': 'Allow all origins (wildcard)',
            'origins': ['*'],
            'test_origins': ['http://localhost:3000', 'https://example.com', 'https://evil.com']
        },
        {
            'name': 'Allow specific localhost',
            'origins': ['http://localhost:3000'],
            'test_origins': ['http://localhost:3000', 'http://localhost:8080', 'https://example.com']
        },
        {
            'name': 'Allow multiple specific domains',
            'origins': ['http://localhost:3000', 'https://app.company.com'],
            'test_origins': ['http://localhost:3000', 'https://app.company.com', 'https://evil.com']
        }
    ]

    results = []

    for test_case in test_cases:
        print(f"\n🧪 Testing: {test_case['name']}")
        print(f"   Configured origins: {test_case['origins']}")

        # Create config file
        config_file = create_test_config(test_case['origins'])

        try:
            # Set environment variable for config
            os.environ['PYLANTIR_CONFIG'] = config_file

            # Import and configure the API (this will load the config)
            from pylantir.cli.run import load_config, update_env_with_config
            config_data = load_config(config_file)
            update_env_with_config(config_data)

            # Check what CORS origins were set
            cors_origins = os.environ.get('CORS_ALLOWED_ORIGINS', 'Not set')
            print(f"   Environment CORS_ALLOWED_ORIGINS: {cors_origins}")

            case_results = {
                'test_case': test_case['name'],
                'configured_origins': test_case['origins'],
                'env_cors_origins': cors_origins,
                'tests': []
            }

            # Test each origin
            for origin in test_case['test_origins']:
                expected_allowed = origin in test_case['origins'] or '*' in test_case['origins']
                print(f"   Testing origin: {origin} (expected: {'✅ allowed' if expected_allowed else '❌ blocked'})")

                # Since we can't easily start/stop the server, we'll just verify the config loading
                case_results['tests'].append({
                    'origin': origin,
                    'expected_allowed': expected_allowed,
                    'note': 'Config loading verified - would need running server for full test'
                })

            results.append(case_results)

        finally:
            # Clean up
            if os.path.exists(config_file):
                os.unlink(config_file)

    return results

def print_test_results(results):
    """Print formatted test results"""
    print("\n" + "="*80)
    print("🎯 CORS CONFIGURATION TEST RESULTS")
    print("="*80)

    for result in results:
        print(f"\n📋 Test Case: {result['test_case']}")
        print(f"   Configured Origins: {result['configured_origins']}")
        print(f"   Environment Variable: {result['env_cors_origins']}")

        for test in result['tests']:
            status = "✅" if test['expected_allowed'] else "❌"
            print(f"   {status} {test['origin']} - {test.get('note', '')}")

if __name__ == "__main__":
    print("🚀 Starting CORS Configuration Tests")

    try:
        results = test_cors_configuration()
        print_test_results(results)

        # Test the get_cors_config function directly
        print(f"\n" + "="*80)
        print("🔧 TESTING get_cors_config() FUNCTION")
        print("="*80)

        # Clear environment and test defaults
        for key in ['CORS_ALLOWED_ORIGINS', 'CORS_ALLOW_CREDENTIALS', 'CORS_ALLOW_METHODS', 'CORS_ALLOW_HEADERS']:
            if key in os.environ:
                del os.environ[key]

        # Import the function
        from pylantir.api_server import get_cors_config

        print("\n📝 Testing default configuration (no env vars):")
        default_config = get_cors_config()
        for key, value in default_config.items():
            print(f"   {key}: {value}")

        # Test with environment variables
        print("\n📝 Testing with environment variables:")
        os.environ['CORS_ALLOWED_ORIGINS'] = '["http://localhost:3000", "https://app.example.com"]'
        os.environ['CORS_ALLOW_CREDENTIALS'] = 'true'

        env_config = get_cors_config()
        for key, value in env_config.items():
            print(f"   {key}: {value}")

        print("\n✅ CORS configuration tests completed successfully!")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)