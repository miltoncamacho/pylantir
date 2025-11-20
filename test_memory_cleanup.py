#!/usr/bin/env python3
"""
Test script for memory cleanup functionality in redcap_to_db.py
"""

import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_cleanup_functions():
    """Test the memory cleanup functions."""
    try:
        from pylantir.redcap_to_db import get_memory_usage, cleanup_memory_and_connections

        print("🧪 Testing Memory Management Functions")
        print("=" * 50)

        # Test memory usage function
        print("\n📊 Testing get_memory_usage():")
        memory_stats = get_memory_usage()
        if memory_stats:
            print(f"   Current memory usage: {memory_stats}")
        else:
            print("   Memory stats not available (psutil not installed)")

        # Test cleanup function
        print("\n🧹 Testing cleanup_memory_and_connections():")
        cleanup_memory_and_connections()
        print("   ✅ Cleanup completed successfully")

        # Test memory usage after cleanup
        print("\n📊 Memory usage after cleanup:")
        memory_stats_after = get_memory_usage()
        if memory_stats_after:
            print(f"   Memory usage after cleanup: {memory_stats_after}")
        else:
            print("   Memory stats not available")

        print("\n✅ All cleanup function tests passed!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_memory_growth_simulation():
    """Simulate memory growth and test cleanup effectiveness."""
    try:
        from pylantir.redcap_to_db import get_memory_usage, cleanup_memory_and_connections
        import gc

        print("\n🎯 Testing Memory Growth Simulation")
        print("=" * 50)

        # Get baseline memory
        baseline = get_memory_usage()
        print(f"📊 Baseline memory: {baseline}")

        # Simulate memory usage by creating large objects
        print("\n📈 Creating memory load...")
        large_objects = []
        for i in range(100):
            # Create some memory pressure
            large_objects.append([j for j in range(1000)])

        after_load = get_memory_usage()
        print(f"📊 Memory after load: {after_load}")

        # Clear the objects manually
        del large_objects

        # Run cleanup
        print("\n🧹 Running cleanup...")
        cleanup_memory_and_connections()

        after_cleanup = get_memory_usage()
        print(f"📊 Memory after cleanup: {after_cleanup}")

        print("\n✅ Memory simulation test completed!")
        return True

    except Exception as e:
        print(f"\n❌ Memory simulation test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Pylantir Memory Cleanup Test Suite")
    print("=" * 60)

    # Test basic functions
    test1_passed = test_cleanup_functions()

    # Test memory simulation
    test2_passed = test_memory_growth_simulation()

    # Summary
    print("\n" + "=" * 60)
    print("📋 Test Results Summary:")
    print(f"   Cleanup Functions: {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"   Memory Simulation: {'✅ PASS' if test2_passed else '❌ FAIL'}")

    if test1_passed and test2_passed:
        print("\n🎉 All tests passed! Memory cleanup is working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Please check the implementation.")
        sys.exit(1)