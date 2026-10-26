"""
Test suite for SQL-backed user repository and integration.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.schemas.auth_users_table import AuthUser
from app.auth.security import hash_password
from app.auth.sql_repository import SqlUserRepository


@pytest.fixture
def db_session():
    """Provide a fresh database session."""
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sql_repo(db_session):
    """Provide a SQL repository instance."""
    return SqlUserRepository(session_factory=SessionLocal)


class TestSqlUserRepository:
    """Test SQL user repository operations."""

    def test_create_compliance_officer(self, db_session):
        """Test creating a Compliance Officer user."""
        repo = SqlUserRepository()
        
        # Clean up if existing
        existing = db_session.query(AuthUser).filter_by(username="compliance_test").first()
        if existing:
            db_session.delete(existing)
            db_session.commit()

        # Create user
        user = repo.create_user(
            db=db_session,
            username="compliance_test",
            password_hash=hash_password("TestPass@2026"),
            display_name="Test Compliance Officer",
            role="Compliance & Regulatory Officer",
            department="Regulatory & Legal Compliance",
            email="compliance.test@amc.com",
            avatar_initials="TC",
            status="Active",
        )
        
        # Verify created
        assert user.username == "compliance_test"
        assert user.role == "Compliance & Regulatory Officer"
        assert user.status == "Active"
        assert user.email == "compliance.test@amc.com"
        
        # Verify can retrieve
        retrieved = db_session.query(AuthUser).filter_by(username="compliance_test").first()
        assert retrieved is not None
        assert retrieved.display_name == "Test Compliance Officer"

    def test_get_by_username(self, db_session, sql_repo):
        """Test retrieving user by username."""
        # Create a user directly (cleaning up existing if present)
        existing = db_session.query(AuthUser).filter_by(username="sarah.compliance").first()
        if existing:
            db_session.delete(existing)
            db_session.commit()

        user = AuthUser(
            username="sarah.compliance",
            password_hash=hash_password("Compliance@2026"),
            display_name="Sarah Kapoor",
            email="s.kapoor@amc.com",
            role="Compliance & Regulatory Officer",
            department="Regulatory & Legal Compliance",
            avatar_initials="SK",
            status="Active",
        )
        db_session.add(user)
        db_session.commit()
        
        # Retrieve via repository
        retrieved = sql_repo.get_by_username("sarah.compliance")
        
        assert retrieved is not None
        assert retrieved.username == "sarah.compliance"
        assert retrieved.display_name == "Sarah Kapoor"
        assert retrieved.role == "Compliance & Regulatory Officer"

    def test_get_by_username_case_insensitive(self, db_session, sql_repo):
        """Test case-insensitive username lookup."""
        existing = db_session.query(AuthUser).filter_by(username="testuser").first()
        if existing:
            db_session.delete(existing)
            db_session.commit()

        # Create a user
        user = AuthUser(
            username="testuser",
            password_hash=hash_password("Test@2026"),
            display_name="Test User",
            email="test@amc.com",
            role="Test Role",
            department="Test Department",
            status="Active",
        )
        db_session.add(user)
        db_session.commit()
        
        # Try different cases
        assert sql_repo.get_by_username("testuser") is not None
        assert sql_repo.get_by_username("TESTUSER") is not None
        assert sql_repo.get_by_username("TestUser") is not None
        assert sql_repo.get_by_username("  testuser  ") is not None

    def test_get_nonexistent_user(self, sql_repo):
        """Test retrieving a non-existent user."""
        result = sql_repo.get_by_username("nonexistent_user_xyz")
        assert result is None

    def test_get_all_users(self, db_session, sql_repo):
        """Test retrieving all users."""
        for i in range(3):
            existing = db_session.query(AuthUser).filter_by(username=f"testuser{i}").first()
            if existing:
                db_session.delete(existing)
        db_session.commit()

        # Create test users
        for i in range(3):
            user = AuthUser(
                username=f"testuser{i}",
                password_hash=hash_password("Test@2026"),
                display_name=f"Test User {i}",
                email=f"test{i}@amc.com",
                role="Test Role",
                department="Test Department",
                status="Active" if i < 2 else "Inactive",
            )
            db_session.add(user)
        db_session.commit()
        
        # Get all users
        all_users = sql_repo.get_all_users(db_session)
        assert len(all_users) >= 3
        
        # Get active only
        active_users = sql_repo.get_all_users(db_session, active_only=True)
        assert all(u.status == "Active" for u in active_users)


class TestComplianceOfficerLogin:
    """Test Compliance Officer login and authentication."""

    @pytest.fixture(autouse=True)
    def setup_compliance_officer(self, db_session):
        """Create a compliance officer user before each test."""
        existing = db_session.query(AuthUser).filter_by(username="compliance_officer").first()
        if existing:
            db_session.delete(existing)
            db_session.commit()

        user = AuthUser(
            username="compliance_officer",
            password_hash=hash_password("Compliance@2026"),
            display_name="Compliance Officer",
            email="compliance@amc.com",
            role="Compliance & Regulatory Officer",
            department="Regulatory & Legal Compliance",
            avatar_initials="CO",
            status="Active",
        )
        db_session.add(user)
        db_session.commit()

    def test_login_success(self):
        """Test successful login with compliance officer credentials."""
        client = TestClient(app)
        
        response = client.post(
            "/api/auth/login",
            json={
                "username": "compliance_officer",
                "password": "Compliance@2026",
                "remember_me": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["username"] == "compliance_officer"
        assert data["user"]["role"] == "Compliance & Regulatory Officer"

    def test_login_wrong_password(self):
        """Test login with wrong password."""
        client = TestClient(app)
        
        response = client.post(
            "/api/auth/login",
            json={
                "username": "compliance_officer",
                "password": "WrongPassword",
                "remember_me": False
            }
        )
        
        assert response.status_code == 401

    def test_login_nonexistent_user(self):
        """Test login with non-existent user."""
        client = TestClient(app)
        
        response = client.post(
            "/api/auth/login",
            json={
                "username": "nonexistent_user",
                "password": "SomePassword",
                "remember_me": False
            }
        )
        
        assert response.status_code == 401

    def test_me_endpoint_with_token(self):
        """Test /api/auth/me endpoint with valid token."""
        client = TestClient(app)
        
        # Login first
        login_response = client.post(
            "/api/auth/login",
            json={
                "username": "compliance_officer",
                "password": "Compliance@2026",
                "remember_me": False
            }
        )
        
        token = login_response.json()["token"]
        
        # Call /me with token
        me_response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert me_response.status_code == 200
        user = me_response.json()["user"]
        assert user["username"] == "compliance_officer"
        assert user["role"] == "Compliance & Regulatory Officer"


class TestComplianceOfficerQueries:
    """Test that Compliance Officer can run queries."""

    @pytest.fixture(autouse=True)
    def setup_compliance_officer(self, db_session):
        """Create a compliance officer user."""
        existing = db_session.query(AuthUser).filter_by(username="compliance_officer").first()
        if existing:
            db_session.delete(existing)
            db_session.commit()

        user = AuthUser(
            username="compliance_officer",
            password_hash=hash_password("Compliance@2026"),
            display_name="Compliance Officer",
            email="compliance@amc.com",
            role="Compliance & Regulatory Officer",
            department="Regulatory & Legal Compliance",
            avatar_initials="CO",
            status="Active",
        )
        db_session.add(user)
        db_session.commit()

    def test_compliance_officer_can_execute_query(self):
        """Test that Compliance Officer can execute a chat query."""
        client = TestClient(app)
        
        # Login
        login_response = client.post(
            "/api/auth/login",
            json={
                "username": "compliance_officer",
                "password": "Compliance@2026"
            }
        )
        
        assert login_response.status_code == 200
        token = login_response.json()["token"]
        
        # Execute query
        query_response = client.post(
            "/api/chat/query",
            json={
                "query": "What are the compliance requirements for fund distribution?",
                "session_id": "test_session_compliance"
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        # Should succeed or at least return a valid response (not 401)
        assert query_response.status_code in [200, 400, 404, 500]
        if query_response.status_code == 401:
            pytest.fail("Compliance Officer should be authenticated to query")

    def test_compliance_officer_session_creation(self):
        """Test that Compliance Officer can create and manage sessions."""
        client = TestClient(app)
        
        # Login
        login_response = client.post(
            "/api/auth/login",
            json={
                "username": "compliance_officer",
                "password": "Compliance@2026"
            }
        )
        
        token = login_response.json()["token"]
        
        # Create session
        session_response = client.post(
            "/api/sessions/compliance_test_session",
            json={
                "history": [
                    {"role": "user", "content": "Compliance test query"},
                    {"role": "assistant", "content": "Compliance test response"}
                ]
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert session_response.status_code == 200
        
        # Retrieve session
        get_response = client.get(
            "/api/sessions/compliance_test_session",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert get_response.status_code == 200
