#!/usr/bin/env python3
"""
Integration test for CORS with a running server
"""
import asyncio
import json
import os
import sys
import tempfile
import subprocess
import time
import signal
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

def create_test_config_strict():
    """Create a strict CORS config for testing"""
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
            "cors_allowed_origins": ["http://localhost:3000"],
            "cors_allow_credentials": True,
            "cors_allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "cors_allow_headers": ["Content-Type", "Authorization"]
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f, indent=2)
        return f.name

async def test_cors_with_curl():
    """Test CORS using curl commands"""
    test_results = []

    # Test preflight with allowed origin
    print("🧪 Testing preflight request with allowed origin (http://localhost:3000)")
    result = subprocess.run([
        "curl", "-s", "-I",
        "-H", "Origin: http://localhost:3000",
        "-H", "Access-Control-Request-Method: GET",
        "-X", "OPTIONS",
        "http://localhost:8000/health"
    ], capture_output=True, text=True)

    if result.returncode == 0:
        headers = result.stdout
        cors_origin = "Access-Control-Allow-Origin: http://localhost:3000" in headers
        cors_methods = "Access-Control-Allow-Methods:" in headers
        cors_credentials = "Access-Control-Allow-Credentials: true" in headers

        test_results.append({
            'test': 'Allowed origin preflight',
            'origin': 'http://localhost:3000',
            'success': cors_origin and cors_methods,
            'details': f"CORS Origin: {cors_origin}, Methods: {cors_methods}, Credentials: {cors_credentials}"
        })
        print(f"   Result: {'✅ PASSED' if cors_origin and cors_methods else '❌ FAILED'}")
        print(f"   Details: {test_results[-1]['details']}")
    else:
        test_results.append({
            'test': 'Allowed origin preflight',
            'origin': 'http://localhost:3000',
            'success': False,
            'details': f"Curl failed: {result.stderr}"
        })
        print(f"   Result: ❌ FAILED - {result.stderr}")

    # Test preflight with blocked origin
    print("\n🧪 Testing preflight request with blocked origin (https://evil.com)")
    result = subprocess.run([
        "curl", "-s", "-I",
        "-H", "Origin: https://evil.com",
        "-H", "Access-Control-Request-Method: GET",
        "-X", "OPTIONS",
        "http://localhost:8000/health"
    ], capture_output=True, text=True)

    if result.returncode == 0:
        headers = result.stdout
        cors_origin = "Access-Control-Allow-Origin: https://evil.com" in headers

        test_results.append({
            'test': 'Blocked origin preflight',
            'origin': 'https://evil.com',
            'success': not cors_origin,  # Success means it's blocked
            'details': f"CORS Origin header present: {cors_origin}"
        })
        print(f"   Result: {'✅ PASSED (blocked)' if not cors_origin else '❌ FAILED (allowed)'}")
        print(f"   Details: {test_results[-1]['details']}")
    else:
        test_results.append({
            'test': 'Blocked origin preflight',
            'origin': 'https://evil.com',
            'success': False,
            'details': f"Curl failed: {result.stderr}"
        })
        print(f"   Result: ❌ FAILED - {result.stderr}")

    return test_results

def main():
    print("🚀 Starting CORS Integration Test with Running Server")

    # Create test config
    config_file = create_test_config_strict()

    try:
        # Start the API server in background
        print(f"📁 Using config file: {config_file}")
        print("🔧 Starting API server...")

        env = os.environ.copy()
        env['PYLANTIR_CONFIG'] = config_file

        # Start server
        server_process = subprocess.Popen([
            "/opt/homebrew/bin/python3.12", "-m", "pylantir.cli.run",
            "start-api", "--pylantir_config", config_file
        ], env=env, cwd="/Users/milton/Desktop/pylantir/src")

        # Wait for server to start
        print("⏳ Waiting for server to start...")
        time.sleep(3)

        # Check if server is running
        health_check = subprocess.run([
            "curl", "-s", "http://localhost:8000/health"
        ], capture_output=True, text=True)

        if health_check.returncode == 0:
            print("✅ Server is running")

            # Run CORS tests
            results = asyncio.run(test_cors_with_curl())

            # Print summary
            print("\n" + "="*80)
            print("📊 CORS INTEGRATION TEST SUMMARY")
            print("="*80)

            passed = sum(1 for r in results if r['success'])
            total = len(results)

            for result in results:
                status = "✅ PASSED" if result['success'] else "❌ FAILED"
                print(f"{status} {result['test']} - {result['origin']}")
                print(f"      {result['details']}")

            print(f"\n🎯 Results: {passed}/{total} tests passed")

            if passed == total:
                print("🎉 All CORS tests PASSED! Configuration is working correctly.")
            else:
                print("⚠️  Some CORS tests failed. Check configuration.")

        else:
            print(f"❌ Server failed to start or health check failed: {health_check.stderr}")

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")

    except Exception as e:
        print(f"❌ Test failed with error: {e}")

    finally:
        # Clean up server
        if 'server_process' in locals():
            print("\n🧹 Cleaning up server...")
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

        # Clean up config file
        if os.path.exists(config_file):
            os.unlink(config_file)

        print("✅ Cleanup completed")

if __name__ == "__main__":
    main()