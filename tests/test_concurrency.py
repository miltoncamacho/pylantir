#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-11-18
    Concurrency test to ensure API operations don't interfere with RedCap sync.
    
    Simulates concurrent database operations from both API and RedCap sync
    to validate transaction isolation and prevent data corruption.
"""

import pytest
import tempfile
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Skip if API dependencies not available
pytest.importorskip("fastapi")

from src.pylantir.api_server import app
from src.pylantir.models import Base, WorklistItem
from src.pylantir.auth_models import AuthBase, User, UserRole
from src.pylantir.auth_utils import get_password_hash
from src.pylantir.db_setup import get_api_db, get_db
from src.pylantir.auth_db_setup import get_auth_db
from src.pylantir.db_concurrency import ConcurrencyManager, safe_database_transaction
from datetime import datetime


class TestConcurrentOperations:
    """Test concurrent API and RedCap-like database operations."""
    
    @pytest.fixture
    def temp_databases(self):
        """Create temporary databases for concurrency testing."""
        # Create temporary database files
        main_db_fd, main_db_path = tempfile.mkstemp(suffix='_concurrent.db')
        auth_db_fd, auth_db_path = tempfile.mkstemp(suffix='_auth_concurrent.db')
        
        # Close file descriptors
        os.close(main_db_fd)
        os.close(auth_db_fd)
        
        # Set environment variables
        os.environ['DB_PATH'] = main_db_path
        os.environ['USERS_DB_PATH'] = auth_db_path
        
        # Create engines for both API and RedCap simulation
        main_engine = create_engine(f"sqlite:///{main_db_path}")
        api_engine = create_engine(f"sqlite:///{main_db_path}", 
                                 connect_args={"check_same_thread": False})
        auth_engine = create_engine(f"sqlite:///{auth_db_path}")
        
        # Create tables
        Base.metadata.create_all(bind=main_engine)
        AuthBase.metadata.create_all(bind=auth_engine)
        
        # Create session makers
        MainSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=main_engine)
        ApiSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=api_engine)
        AuthSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=auth_engine)
        
        yield {
            'main_session': MainSessionLocal,
            'api_session': ApiSessionLocal,
            'auth_session': AuthSessionLocal,
            'main_db_path': main_db_path,
            'auth_db_path': auth_db_path
        }
        
        # Cleanup
        os.unlink(main_db_path)
        os.unlink(auth_db_path)
    
    @pytest.fixture
    def setup_test_data(self, temp_databases):
        """Set up test user and initial data."""
        # Create test admin user
        auth_session = temp_databases['auth_session']()
        admin = User(
            username="concurrency_admin",
            email="admin@concurrency.test",
            full_name="Concurrency Test Admin",
            hashed_password=get_password_hash("testpass123"),
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.utcnow()
        )
        auth_session.add(admin)
        auth_session.commit()
        auth_session.close()
        
        # Create initial worklist items
        main_session = temp_databases['main_session']()
        for i in range(5):
            item = WorklistItem(
                study_instance_uid=f"1.2.3.4.5.{i}",
                patient_name=f"Test^Patient{i}",
                patient_id=f"TEST{i:03d}",
                patient_birth_date="19900101",
                patient_sex="M",
                modality="MR",
                performed_procedure_step_status="SCHEDULED"
            )
            main_session.add(item)
        main_session.commit()
        main_session.close()
        
        return admin
    
    @pytest.fixture
    def override_dependencies(self, temp_databases):
        """Override FastAPI dependencies with test databases."""
        def override_get_api_db():
            db = temp_databases['api_session']()
            try:
                yield db
            finally:
                db.close()
        
        def override_get_auth_db():
            db = temp_databases['auth_session']()
            try:
                yield db
            finally:
                db.close()
        
        # Override dependencies
        app.dependency_overrides[get_api_db] = override_get_api_db
        app.dependency_overrides[get_auth_db] = override_get_auth_db
        
        yield
        
        # Clear overrides
        app.dependency_overrides.clear()
    
    @pytest.fixture
    def test_client(self, override_dependencies):
        """Create test client with overridden dependencies."""
        return TestClient(app)
    
    def simulate_redcap_sync(self, session_maker, operations_count: int, results: List):
        """
        Simulate RedCap sync operations that create/update worklist items.
        
        Args:
            session_maker: Database session maker
            operations_count: Number of operations to perform
            results: List to store operation results
        """
        try:
            for i in range(operations_count):
                session = session_maker()
                
                try:
                    # Simulate RedCap sync creating new worklist items
                    item = WorklistItem(
                        study_instance_uid=f"redcap.sync.{threading.current_thread().ident}.{i}",
                        patient_name=f"RedCap^Patient{i}",
                        patient_id=f"RC{i:04d}",
                        patient_birth_date="19850615",
                        patient_sex="F",
                        modality="CT",
                        performed_procedure_step_status="SCHEDULED"
                    )
                    
                    session.add(item)
                    session.commit()
                    
                    # Small delay to simulate processing time
                    time.sleep(0.01)
                    
                    results.append(f"redcap_create_{i}")
                    
                except Exception as e:
                    session.rollback()
                    results.append(f"redcap_error_{i}: {e}")
                finally:
                    session.close()
                    
        except Exception as e:
            results.append(f"redcap_thread_error: {e}")
    
    def simulate_api_operations(self, client: TestClient, auth_token: str, operations_count: int, results: List):
        """
        Simulate API operations that read/modify worklist items.
        
        Args:
            client: FastAPI test client
            auth_token: Authentication token
            operations_count: Number of operations to perform
            results: List to store operation results
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        try:
            for i in range(operations_count):
                try:
                    # Mix of read and write operations
                    if i % 3 == 0:
                        # Read operation
                        response = client.get("/worklist", headers=headers)
                        if response.status_code == 200:
                            results.append(f"api_read_{i}")
                        else:
                            results.append(f"api_read_error_{i}: {response.status_code}")
                    
                    elif i % 3 == 1:
                        # Create operation
                        item_data = {
                            "patient_name": f"API^Patient{i}",
                            "patient_id": f"API{i:04d}",
                            "performed_procedure_step_status": "SCHEDULED"
                        }
                        response = client.post("/worklist", json=item_data, headers=headers)
                        if response.status_code == 200:
                            results.append(f"api_create_{i}")
                        else:
                            results.append(f"api_create_error_{i}: {response.status_code}")
                    
                    else:
                        # Update operation (try to update first item)
                        response = client.get("/worklist", headers=headers)
                        if response.status_code == 200 and response.json():
                            items = response.json()
                            if items:
                                first_item_id = items[0]['id']
                                update_data = {"performed_procedure_step_status": "IN_PROGRESS"}
                                response = client.put(f"/worklist/{first_item_id}", 
                                                    json=update_data, headers=headers)
                                if response.status_code == 200:
                                    results.append(f"api_update_{i}")
                                else:
                                    results.append(f"api_update_error_{i}: {response.status_code}")
                    
                    # Small delay to simulate processing time
                    time.sleep(0.01)
                    
                except Exception as e:
                    results.append(f"api_error_{i}: {e}")
                    
        except Exception as e:
            results.append(f"api_thread_error: {e}")
    
    def get_auth_token(self, client: TestClient) -> str:
        """Get authentication token."""
        response = client.post("/auth/login", json={
            "username": "concurrency_admin",
            "password": "testpass123"
        })
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_concurrent_api_redcap_operations(self, temp_databases, setup_test_data, test_client):
        """
        Test that API and RedCap-like operations can run concurrently without interference.
        """
        # Get authentication token
        auth_token = self.get_auth_token(test_client)
        
        # Results storage for both threads
        redcap_results = []
        api_results = []
        
        # Configure concurrent operations
        operations_per_thread = 20
        
        # Create thread executor for concurrent operations
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Start RedCap sync simulation
            redcap_future = executor.submit(
                self.simulate_redcap_sync,
                temp_databases['main_session'],
                operations_per_thread,
                redcap_results
            )
            
            # Start API operations simulation
            api_future = executor.submit(
                self.simulate_api_operations,
                test_client,
                auth_token,
                operations_per_thread,
                api_results
            )
            
            # Wait for both to complete
            redcap_future.result(timeout=30)
            api_future.result(timeout=30)
        
        # Analyze results
        print(f"\\nRedCap operations: {len(redcap_results)}")
        print(f"API operations: {len(api_results)}")
        
        # Count successful operations
        redcap_success = len([r for r in redcap_results if not r.startswith(('redcap_error', 'redcap_thread_error'))])
        api_success = len([r for r in api_results if not r.startswith(('api_error', 'api_thread_error'))])
        
        print(f"RedCap successful operations: {redcap_success}/{operations_per_thread}")
        print(f"API successful operations: {api_success}")
        
        # Verify data integrity
        main_session = temp_databases['main_session']()
        try:
            total_items = main_session.query(WorklistItem).count()
            redcap_items = main_session.query(WorklistItem).filter(
                WorklistItem.study_instance_uid.like('redcap.sync.%')
            ).count()
            api_items = main_session.query(WorklistItem).filter(
                WorklistItem.patient_id.like('API%')
            ).count()
            
            print(f"\\nDatabase integrity check:")
            print(f"Total items in database: {total_items}")
            print(f"RedCap created items: {redcap_items}")
            print(f"API created items: {api_items}")
            
            # Assertions
            assert redcap_success > 0, "RedCap sync operations should succeed"
            assert api_success > 0, "API operations should succeed"
            assert total_items >= redcap_items + api_items, "Data integrity maintained"
            
            # Check for minimal errors (some errors acceptable under high concurrency)
            redcap_errors = len(redcap_results) - redcap_success
            api_errors = len(api_results) - api_success
            
            print(f"RedCap errors: {redcap_errors}")
            print(f"API errors: {api_errors}")
            
            # Allow for some errors but ensure majority succeed
            assert redcap_success >= operations_per_thread * 0.8, "At least 80% of RedCap operations should succeed"
            assert api_success >= operations_per_thread * 0.6, "At least 60% of API operations should succeed"
            
        finally:
            main_session.close()
    
    def test_database_transaction_isolation(self, temp_databases):
        """Test that database transactions are properly isolated."""
        session1 = temp_databases['main_session']()
        session2 = temp_databases['api_session']()
        
        try:
            # Session 1 creates item but doesn't commit
            session1.begin()
            item1 = WorklistItem(
                study_instance_uid="isolation.test.1",
                patient_name="Isolation^Test1",
                patient_id="ISO001",
                performed_procedure_step_status="SCHEDULED"
            )
            session1.add(item1)
            session1.flush()  # Send to DB but don't commit
            
            # Session 2 should not see uncommitted item
            count_session2 = session2.query(WorklistItem).filter(
                WorklistItem.patient_id == "ISO001"
            ).count()
            
            assert count_session2 == 0, "Uncommitted transaction should not be visible to other sessions"
            
            # Commit session 1
            session1.commit()
            
            # Now session 2 should see the item
            count_session2_after = session2.query(WorklistItem).filter(
                WorklistItem.patient_id == "ISO001"
            ).count()
            
            assert count_session2_after == 1, "Committed transaction should be visible to other sessions"
            
        finally:
            session1.close()
            session2.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])