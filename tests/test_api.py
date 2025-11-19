#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-11-18
    Integration tests for Pylantir FastAPI endpoints.
    
    Tests authentication, authorization, and CRUD operations
    for both worklist items and user management.
"""

import pytest
import json
import tempfile
import os
from typing import Dict, Any
from datetime import datetime

from jose import jwt

# Only run these tests if API dependencies are available
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.pylantir.api_server import app, get_current_user, get_auth_db
from src.pylantir.auth_models import AuthBase, User, UserRole
from src.pylantir.auth_utils import get_password_hash, SECRET_KEY, ALGORITHM
from src.pylantir.models import Base, WorklistItem
from src.pylantir.db_setup import get_api_db


class TestPylantirAPI:
    """Test class for Pylantir API endpoints."""
    
    @pytest.fixture
    def temp_databases(self):
        """Create temporary databases for testing."""
        # Create temporary database files
        main_db_fd, main_db_path = tempfile.mkstemp(suffix='.db')
        auth_db_fd, auth_db_path = tempfile.mkstemp(suffix='.db')
        
        # Close file descriptors
        os.close(main_db_fd)
        os.close(auth_db_fd)
        
        # Set environment variables for test databases
        os.environ['DB_PATH'] = main_db_path
        os.environ['USERS_DB_PATH'] = auth_db_path
        
        # Create engines
        main_engine = create_engine(f"sqlite:///{main_db_path}")
        auth_engine = create_engine(f"sqlite:///{auth_db_path}")
        
        # Create tables
        Base.metadata.create_all(bind=main_engine)
        AuthBase.metadata.create_all(bind=auth_engine)
        
        # Create session makers
        MainSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=main_engine)
        AuthSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=auth_engine)
        
        yield {
            'main_engine': main_engine,
            'auth_engine': auth_engine,
            'main_session': MainSessionLocal,
            'auth_session': AuthSessionLocal,
            'main_db_path': main_db_path,
            'auth_db_path': auth_db_path
        }
        
        # Cleanup
        os.unlink(main_db_path)
        os.unlink(auth_db_path)
    
    @pytest.fixture
    def override_dependencies(self, temp_databases):
        """Override FastAPI dependencies with test databases."""
        def override_get_db():
            db = temp_databases['main_session']()
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
        app.dependency_overrides[get_api_db] = override_get_db
        app.dependency_overrides[get_auth_db] = override_get_auth_db
        
        yield
        
        # Clear overrides
        app.dependency_overrides.clear()
    
    @pytest.fixture
    def test_client(self, override_dependencies):
        """Create test client with overridden dependencies."""
        return TestClient(app)
    
    @pytest.fixture
    def admin_user(self, temp_databases):
        """Create test admin user."""
        auth_session = temp_databases['auth_session']()
        
        admin = User(
            username="testadmin",
            email="admin@test.com",
            full_name="Test Admin",
            hashed_password=get_password_hash("testpassword123"),
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        auth_session.add(admin)
        auth_session.commit()
        auth_session.refresh(admin)
        auth_session.close()
        
        return admin
    
    @pytest.fixture 
    def read_user(self, temp_databases):
        """Create test read-only user."""
        auth_session = temp_databases['auth_session']()
        
        reader = User(
            username="testread",
            email="read@test.com",
            full_name="Test Reader",
            hashed_password=get_password_hash("readpassword123"),
            role=UserRole.READ,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        auth_session.add(reader)
        auth_session.commit()
        auth_session.refresh(reader)
        auth_session.close()
        
        return reader
    
    @pytest.fixture
    def sample_worklist_item(self, temp_databases):
        """Create sample worklist item for testing."""
        main_session = temp_databases['main_session']()
        
        item = WorklistItem(
            study_instance_uid="1.2.3.4.5.6.7.8.9.10",
            patient_name="Test^Patient",
            patient_id="TEST001",
            patient_birth_date="19900101",
            patient_sex="M",
            patient_weight_lb="70",
            accession_number="ACC001",
            referring_physician_name="Dr. Test",
            modality="MR",
            study_description="Test Study",
            scheduled_start_date="20231118",
            scheduled_start_time="140000",
            performed_procedure_step_status="SCHEDULED"
        )
        
        main_session.add(item)
        main_session.commit()
        main_session.refresh(item)
        main_session.close()
        
        return item
    
    def get_auth_token(self, client: TestClient, username: str, password: str) -> str:
        """Get authentication token for user."""
        response = client.post("/auth/login", json={
            "username": username,
            "password": password
        })
        assert response.status_code == 200
        return response.json()["access_token"]
    
    def test_health_check(self, test_client):
        """Test health check endpoint."""
        response = test_client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json()
        assert response.json()["status"] == "healthy"
    
    def test_login_success(self, test_client, admin_user):
        """Test successful login."""
        response = test_client.post("/auth/login", json={
            "username": "testadmin",
            "password": "testpassword123"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_custom_expiration(self, test_client, admin_user):
        """Test login with custom token expiration."""
        expire_minutes = 10
        response = test_client.post("/auth/login", json={
            "username": "testadmin",
            "password": "testpassword123",
            "access_token_expire_minutes": expire_minutes
        })

        assert response.status_code == 200
        data = response.json()
        token = data["access_token"]

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"verify_exp": False}
        )

        exp_timestamp = payload.get("exp")
        assert exp_timestamp is not None
        expires_in = (datetime.utcfromtimestamp(exp_timestamp) - datetime.utcnow()).total_seconds()
        assert abs(expires_in - expire_minutes * 60) < 20
    
    def test_login_invalid_credentials(self, test_client):
        """Test login with invalid credentials."""
        response = test_client.post("/auth/login", json={
            "username": "invalid",
            "password": "invalid"
        })
        
        assert response.status_code == 401
        assert "Invalid username or password" in response.json()["detail"]
    
    def test_get_worklist_unauthorized(self, test_client):
        """Test accessing worklist without authentication."""
        response = test_client.get("/worklist")
        assert response.status_code == 403  # FastAPI HTTPBearer returns 403 when no credentials provided
    
    def test_get_worklist_authorized(self, test_client, admin_user, sample_worklist_item):
        """Test accessing worklist with authentication."""
        token = self.get_auth_token(test_client, "testadmin", "testpassword123")
        headers = {"Authorization": f"Bearer {token}"}
        
        response = test_client.get("/worklist", headers=headers)
        assert response.status_code == 200
        
        items = response.json()
        assert isinstance(items, list)
        assert len(items) == 1
        assert items[0]["patient_id"] == "TEST001"
    
    def test_get_worklist_with_status_filter(self, test_client, admin_user, sample_worklist_item):
        """Test worklist filtering by status."""
        token = self.get_auth_token(test_client, "testadmin", "testpassword123")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test with SCHEDULED status
        response = test_client.get("/worklist?status=SCHEDULED", headers=headers)
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        
        # Test with COMPLETED status (should return empty)
        response = test_client.get("/worklist?status=COMPLETED", headers=headers)
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 0
    
    def test_create_worklist_item_admin(self, test_client, admin_user):
        """Test creating worklist item as admin."""
        token = self.get_auth_token(test_client, "testadmin", "testpassword123")
        headers = {"Authorization": f"Bearer {token}"}
        
        item_data = {
            "patient_name": "New^Patient",
            "patient_id": "NEW001",
            "patient_birth_date": "19850615",
            "patient_sex": "F",
            "modality": "CT",
            "performed_procedure_step_status": "SCHEDULED"
        }
        
        response = test_client.post("/worklist", json=item_data, headers=headers)
        assert response.status_code == 200
        
        created_item = response.json()
        assert created_item["patient_id"] == "NEW001"
        assert created_item["patient_name"] == "New^Patient"
        assert "study_instance_uid" in created_item
    
    def test_create_worklist_item_read_user_forbidden(self, test_client, read_user):
        """Test that read-only user cannot create worklist items."""
        token = self.get_auth_token(test_client, "testread", "readpassword123")
        headers = {"Authorization": f"Bearer {token}"}
        
        item_data = {
            "patient_name": "New^Patient",
            "patient_id": "NEW001",
            "performed_procedure_step_status": "SCHEDULED"
        }
        
        response = test_client.post("/worklist", json=item_data, headers=headers)
        assert response.status_code == 403
    
    def test_update_worklist_item(self, test_client, admin_user, sample_worklist_item):
        """Test updating worklist item."""
        token = self.get_auth_token(test_client, "testadmin", "testpassword123")
        headers = {"Authorization": f"Bearer {token}"}
        
        update_data = {
            "performed_procedure_step_status": "IN_PROGRESS",
            "modality": "MR"
        }
        
        response = test_client.put(f"/worklist/{sample_worklist_item.id}", 
                                 json=update_data, headers=headers)
        assert response.status_code == 200
        
        updated_item = response.json()
        assert updated_item["performed_procedure_step_status"] == "IN_PROGRESS"
    
    def test_delete_worklist_item(self, test_client, admin_user, sample_worklist_item):
        """Test deleting worklist item."""
        token = self.get_auth_token(test_client, "testadmin", "testpassword123")
        headers = {"Authorization": f"Bearer {token}"}
        
        response = test_client.delete(f"/worklist/{sample_worklist_item.id}", 
                                    headers=headers)
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]
    
    def test_get_users_admin_only(self, test_client, admin_user, read_user):
        """Test that only admin can access user list."""
        # Test with admin user
        admin_token = self.get_auth_token(test_client, "testadmin", "testpassword123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        
        response = test_client.get("/users", headers=admin_headers)
        assert response.status_code == 200
        
        users = response.json()
        assert isinstance(users, list)
        assert len(users) == 2  # admin + read user
        
        # Test with read user (should be forbidden)
        read_token = self.get_auth_token(test_client, "testread", "readpassword123")
        read_headers = {"Authorization": f"Bearer {read_token}"}
        
        response = test_client.get("/users", headers=read_headers)
        assert response.status_code == 403
    
    def test_create_user_admin_only(self, test_client, admin_user):
        """Test creating new user (admin only)."""
        token = self.get_auth_token(test_client, "testadmin", "testpassword123")
        headers = {"Authorization": f"Bearer {token}"}
        
        user_data = {
            "username": "newuser",
            "email": "newuser@test.com",
            "full_name": "New User",
            "password": "newpassword123",
            "role": "write"
        }
        
        response = test_client.post("/users", json=user_data, headers=headers)
        assert response.status_code == 200
        
        created_user = response.json()
        assert created_user["username"] == "newuser"
        assert created_user["role"] == "write"
        assert "hashed_password" not in created_user  # Password should not be returned
    
    def test_create_duplicate_username(self, test_client, admin_user):
        """Test creating user with duplicate username."""
        token = self.get_auth_token(test_client, "testadmin", "testpassword123")
        headers = {"Authorization": f"Bearer {token}"}
        
        user_data = {
            "username": "testadmin",  # Already exists
            "password": "newpassword123",
            "role": "read"
        }
        
        response = test_client.post("/users", json=user_data, headers=headers)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])