"""ConnectRPC compatibility layer.

This module provides a Python 3.12 compatible implementation of the
connectrpc library interfaces used by LlamaTrade services.

The official connectrpc package requires Python 3.13+, so we provide
a minimal implementation here for compatibility.
"""

from connectrpc.code import Code
from connectrpc.errors import ConnectError

__all__ = ["Code", "ConnectError"]
