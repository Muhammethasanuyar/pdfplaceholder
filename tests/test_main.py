import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import os

from fastapi.testclient import TestClient
from fastapi import UploadFile
import fitz

from main import app, check_rate_limit, validate_file_size, generate_task_id
from main import rate_limit_cache, MAX_FILE_SIZE_MB, MAX_REQUESTS_PER_MINUTE


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def sample_pdf():
    """Create a simple PDF for testing"""
    # Create a simple PDF with placeholder
    doc = fitz.open()
    page = doc.new_page()

    # Add some text with placeholder
    text = "Merhaba {{ad_soyad}}, nasılsınız?"
    rect = fitz.Rect(50, 50, 400, 80)
    page.insert_textbox(rect, text, fontsize=12)

    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        doc.save(tmp.name)
        doc.close()
        yield tmp.name
        os.unlink(tmp.name)


class TestRateLimiting:
    """Test rate limiting functionality"""

    def setup_method(self):
        """Reset rate limit cache before each test"""
        rate_limit_cache.clear()

    def test_rate_limit_under_limit(self):
        """Test rate limiting when under the limit"""
        client_ip = "192.168.1.1"

        # Should allow requests under the limit
        for _ in range(MAX_REQUESTS_PER_MINUTE - 1):
            assert check_rate_limit(client_ip) is True

        assert len(rate_limit_cache[client_ip]) == MAX_REQUESTS_PER_MINUTE - 1

    def test_rate_limit_at_limit(self):
        """Test rate limiting when at the limit"""
        client_ip = "192.168.1.1"

        # Fill up to the limit
        for _ in range(MAX_REQUESTS_PER_MINUTE):
            assert check_rate_limit(client_ip) is True

        # Next request should be blocked
        assert check_rate_limit(client_ip) is False

    def test_rate_limit_cleanup(self):
        """Test that old entries are cleaned up"""
        client_ip = "192.168.1.1"

        # Add old entry
        old_time = datetime.now() - timedelta(minutes=2)
        rate_limit_cache[client_ip] = [old_time]

        # Should allow new request after cleanup
        assert check_rate_limit(client_ip) is True
        assert len(rate_limit_cache[client_ip]) == 1


class TestFileValidation:
    """Test file validation functionality"""

    def test_valid_file_size(self):
        """Test file size validation with valid size"""
        data = b"x" * (1024 * 1024)  # 1MB
        validate_file_size(data)  # Should not raise

    def test_invalid_file_size(self):
        """Test file size validation with invalid size"""
        data = b"x" * (int(MAX_FILE_SIZE_MB + 1) * 1024 * 1024)  # Over limit

        with pytest.raises(Exception) as exc_info:
            validate_file_size(data)

        assert "maksimum" in str(exc_info.value.detail)


class TestAPIEndpoints:
    """Test API endpoints"""

    def test_ocr_status(self, client):
        """Test OCR status endpoint"""
        response = client.get("/ocr_status")
        assert response.status_code == 200
        data = response.json()
        assert "tesseract_cmd" in data
        assert "available" in data

    def test_analyze_invalid_file(self, client):
        """Test analyze endpoint with invalid file type"""
        response = client.post("/analyze", files={"template": ("test.txt", b"not a pdf", "text/plain")})
        assert response.status_code == 400

    @patch("main.has_text_layer")
    @patch("main.collect_placeholders")
    def test_analyze_valid_pdf(self, mock_collect, mock_has_text, client, sample_pdf):
        """Test analyze endpoint with valid PDF"""
        mock_has_text.return_value = True
        mock_collect.return_value = [
            {"key": "ad_soyad", "rect": fitz.Rect(0, 0, 100, 20), "page": 0}
        ]

        with open(sample_pdf, "rb") as f:
            response = client.post("/analyze", files={"template": ("test.pdf", f, "application/pdf")})

        assert response.status_code == 200
        data = response.json()
        assert data["pages"] >= 0
        assert "placeholders" in data
        assert "unique_keys" in data

    def test_fill_invalid_json(self, client, sample_pdf):
        """Test fill endpoint with invalid JSON"""
        with open(sample_pdf, "rb") as f:
            response = client.post("/fill", data={
                "template": ("test.pdf", f, "application/pdf"),
                "fields_json": "invalid json",
                "align_json": "{}"
            })

        assert response.status_code == 400

    def test_task_status_not_found(self, client):
        """Test task status endpoint with non-existent task"""
        response = client.get("/task/non_existent_task")
        assert response.status_code == 404


class TestUtilityFunctions:
    """Test utility functions"""

    def test_generate_task_id(self):
        """Test task ID generation"""
        task_id1 = generate_task_id()
        task_id2 = generate_task_id()

        assert task_id1 != task_id2
        assert task_id1.startswith("task_")
        assert task_id2.startswith("task_")


class TestBackgroundTasks:
    """Test background task functionality"""

    @patch("main.process_fill_request")
    def test_background_task_creation(self, mock_process, client, sample_pdf):
        """Test background task creation"""
        mock_process.return_value = ("/tmp/test.pdf", {}, [])

        with open(sample_pdf, "rb") as f:
            response = client.post("/fill", data={
                "template": ("test.pdf", f, "application/pdf"),
                "fields_json": '{"ad_soyad": "Test User"}',
                "align_json": "{}",
                "async_process": "1"
            })

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "queued"

    def test_task_status_endpoint(self, client):
        """Test task status endpoint"""
        # First create a mock task
        from main import background_tasks
        task_id = "test_task_123"
        background_tasks[task_id] = {
            "status": "completed",
            "created_at": datetime.now(),
            "client_ip": "127.0.0.1",
            "file_size": 1024
        }

        response = client.get(f"/task/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["client_ip"] == "127.0.0.1"


if __name__ == "__main__":
    pytest.main([__file__])




