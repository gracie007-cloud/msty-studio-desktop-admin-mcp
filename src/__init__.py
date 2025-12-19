"""
Msty Admin MCP Server

AI-administered Msty Studio Desktop management system.

Phase 1: Foundational Tools (Read-Only)
Phase 2: Configuration Management (Planned)
Phase 3: Automation Bridge (Planned)
Phase 4: Intelligence Layer (Planned)

Created by Pineapple 🍍
"""

__version__ = "2.0.0"
__author__ = "Pineapple 🍍"

from .server import mcp, main

__all__ = ["mcp", "main", "__version__", "__author__"]