#!/usr/bin/env python3
"""
Debug CORS headers - check what the server is actually sending
"""
import subprocess
import json
import os
import tempfile

def create_test_config():
    """Create a strict CORS config"""
    config = {
        "db_path": ":memory:",
        "db_echo": "0",
        "db_update_interval": 60,
        "allowed_aet": [],
        "operation_interval": {"start_time": [0, 0], "end_time": [23, 59]},
        "mri_visit_session_mapping": {"t1_arm_1": "1"},
        "site": "792",
        "redcap2wl": {},
        "protocol": {"792": "BRAIN_MRI_3T"},
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

def test_cors_headers():
    print("🔍 Testing CORS headers directly")

    # Test with allowed origin
    print("\n📡 Testing OPTIONS request with allowed origin:")
    result = subprocess.run([
        "curl", "-v", "-X", "OPTIONS",
        "-H", "Origin: http://localhost:3000",
        "-H", "Access-Control-Request-Method: GET",
        "http://localhost:8000/health"
    ], capture_output=True, text=True)

    print("📤 Request headers sent:")
    print("   Origin: http://localhost:3000")
    print("   Access-Control-Request-Method: GET")

    print(f"\n📥 Response status: {result.returncode}")
    print("📥 Response headers:")
    for line in result.stderr.split('\n'):
        if 'Access-Control' in line or 'access-control' in line.lower():
            print(f"   {line.strip()}")

    # Test simple GET request
    print("\n📡 Testing simple GET request with Origin:")
    result = subprocess.run([
        "curl", "-v", "-H", "Origin: http://localhost:3000",
        "http://localhost:8000/health"
    ], capture_output=True, text=True)

    print("📤 Request headers sent:")
    print("   Origin: http://localhost:3000")

    print(f"\n📥 Response status: {result.returncode}")
    print("📥 Response headers:")
    for line in result.stderr.split('\n'):
        if 'Access-Control' in line or 'access-control' in line.lower():
            print(f"   {line.strip()}")

if __name__ == "__main__":
    print("🧪 CORS Header Debug Test")
    print("⚠️  Make sure the API server is running on http://localhost:8000")
    print("   Run: python -m pylantir.cli.run start-api --pylantir_config your_config.json")

    # Server should be running - no input needed

    test_cors_headers()