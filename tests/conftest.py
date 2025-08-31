import pytest
import tempfile
import os
from pathlib import Path

@pytest.fixture(scope="session")
def test_data_dir():
    """Test data directory fixture"""
    return Path(__file__).parent / "data"

@pytest.fixture(scope="session")
def sample_pdf_path(test_data_dir):
    """Path to sample PDF template"""
    return test_data_dir / "sample_template.pdf"

@pytest.fixture
def temp_dir():
    """Temporary directory fixture"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def mock_logger():
    """Mock logger for testing"""
    class MockLogger:
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass
        def debug(self, msg): pass

    return MockLogger()




