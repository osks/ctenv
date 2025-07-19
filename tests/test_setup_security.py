"""Security tests for the setup command."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

from ctenv import cmd_setup, calculate_sha256


@pytest.mark.unit
def test_calculate_sha256():
    """Test SHA256 calculation function."""
    # Create a test file with known content
    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
        f.write(b"Hello, World!")
        test_file = Path(f.name)
    
    try:
        # Known SHA256 for "Hello, World!"
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        actual = calculate_sha256(test_file)
        assert actual == expected
    finally:
        test_file.unlink()


@pytest.mark.unit
def test_setup_checksum_verification_success(capsys):
    """Test successful checksum verification during setup."""
    # Mock args
    args = MagicMock()
    args.force = False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override ctenv directory
        with patch('ctenv.Path.home') as mock_home:
            mock_home.return_value = Path(tmpdir)
            
            # Mock successful download
            def mock_urlretrieve(url, path):
                # Write a fake binary with known content
                with open(path, 'wb') as f:
                    f.write(b"fake gosu binary content")
            
            with patch('urllib.request.urlretrieve', side_effect=mock_urlretrieve):
                # Calculate checksum for our fake content
                ctenv_dir = Path(tmpdir) / ".ctenv"
                ctenv_dir.mkdir(exist_ok=True)
                test_file = ctenv_dir / "test"
                test_file.write_bytes(b"fake gosu binary content")
                fake_checksum = calculate_sha256(test_file)
                test_file.unlink()
                
                with patch.dict('ctenv.GOSU_CHECKSUMS', {
                    "gosu-amd64": fake_checksum,
                    "gosu-arm64": fake_checksum
                }, clear=False):
                    # Run setup
                    cmd_setup(args)
    
    captured = capsys.readouterr()
    assert "Downloaded and verified" in captured.out
    assert "✓" in captured.out


@pytest.mark.unit
def test_setup_checksum_verification_failure(capsys):
    """Test failed checksum verification during setup."""
    # Mock args
    args = MagicMock()
    args.force = False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override ctenv directory
        with patch('ctenv.Path.home') as mock_home:
            mock_home.return_value = Path(tmpdir)
            
            # Mock successful download but with wrong content
            def mock_urlretrieve(url, path):
                with open(path, 'wb') as f:
                    f.write(b"malicious content")
            
            with patch('urllib.request.urlretrieve', side_effect=mock_urlretrieve):
                # Use the real checksums which won't match our fake content
                with pytest.raises(SystemExit):
                    cmd_setup(args)
    
    captured = capsys.readouterr()
    assert "Checksum verification failed" in captured.out
    assert "Expected:" in captured.out
    assert "Got:" in captured.out
    
    # Verify the files were deleted
    ctenv_dir = Path(tmpdir) / ".ctenv"
    assert not (ctenv_dir / "gosu-amd64").exists()
    assert not (ctenv_dir / "gosu-arm64").exists()


@pytest.mark.unit
def test_setup_download_failure(capsys):
    """Test handling of download failures."""
    # Mock args
    args = MagicMock()
    args.force = False
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override ctenv directory
        with patch('ctenv.Path.home') as mock_home:
            mock_home.return_value = Path(tmpdir)
            
            # Mock download failure
            with patch('urllib.request.urlretrieve', 
                      side_effect=urllib.error.URLError("Network error")):
                with pytest.raises(SystemExit):
                    cmd_setup(args)
    
    captured = capsys.readouterr()
    assert "Failed to download" in captured.out
    assert "Network error" in captured.out


@pytest.mark.unit
def test_setup_force_redownload(capsys):
    """Test force flag to redownload existing binaries."""
    # Mock args
    args = MagicMock()
    args.force = True
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Override ctenv directory  
        with patch('ctenv.Path.home') as mock_home:
            mock_home.return_value = Path(tmpdir)
            
            # Create existing binaries
            ctenv_dir = Path(tmpdir) / ".ctenv"
            ctenv_dir.mkdir()
            (ctenv_dir / "gosu-amd64").write_text("old content")
            (ctenv_dir / "gosu-arm64").write_text("old content")
            
            # Mock successful download
            def mock_urlretrieve(url, path):
                with open(path, 'wb') as f:
                    f.write(b"new binary content")
            
            with patch('urllib.request.urlretrieve', side_effect=mock_urlretrieve):
                # Calculate checksum for new content
                test_file = ctenv_dir / "test"
                test_file.write_bytes(b"new binary content")
                new_checksum = calculate_sha256(test_file)
                test_file.unlink()
                
                with patch.dict('ctenv.GOSU_CHECKSUMS', {
                    "gosu-amd64": new_checksum,
                    "gosu-arm64": new_checksum
                }, clear=False):
                    cmd_setup(args)
    
    captured = capsys.readouterr()
    # Should download even though files exist
    assert "Downloaded and verified" in captured.out
    assert "already exists" not in captured.out