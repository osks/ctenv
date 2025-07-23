"""Security tests for checksum utilities."""

import pytest
import tempfile
from pathlib import Path

from ctenv.cli import calculate_sha256


@pytest.mark.unit
def test_calculate_sha256():
    """Test SHA256 calculation function."""
    # Create a test file with known content
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        f.write(b"Hello, World!")
        test_file = Path(f.name)

    try:
        # Known SHA256 for "Hello, World!"
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        actual = calculate_sha256(test_file)
        assert actual == expected
    finally:
        test_file.unlink()
