"""ctenv - Run programs in containers as current user"""

__version__ = "0.1.0"

# Import the main function but don't override the module namespace
from ctenv.cli import main

# Expose main for the entry point
__all__ = ["main", "__version__"]
