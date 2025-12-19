#!/usr/bin/env python3
"""
Msty Admin MCP Server

AI-administered Msty Studio Desktop management system with database insights,
configuration management, hardware optimization, and Claude Desktop sync.

Phase 1: Foundational Tools (Read-Only)
- detect_msty_installation
- read_msty_database
- list_configured_tools
- get_model_providers
- analyse_msty_health

Created by Pineapple 🍍 AI Administration System
"""

import json
import logging
import os
import platform
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import psutil
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("msty-admin-mcp")

# Initialize FastMCP server
mcp = FastMCP("msty-admin")

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class MstyInstallation:
    """Msty Studio Desktop installation details"""
    installed: bool
    version: Optional[str] = None
    app_path: Optional[str] = None
    data_path: Optional[str] = None
    sidecar_path: Optional[str] = None
    database_path: Optional[str] = None
    mlx_models_path: Optional[str] = None
    is_running: bool = False
    sidecar_running: bool = False
    platform_info: dict = field(default_factory=dict)


@dataclass
class MstyHealthReport:
    """Msty Studio health analysis"""
    overall_status: str  # healthy, warning, critical
    database_status: dict = field(default_factory=dict)
    storage_status: dict = field(default_factory=dict)
    model_cache_status: dict = field(default_factory=dict)
    recommendations: list = field(default_factory=list)
    timestamp: str = ""


@dataclass
class DatabaseStats:
    """Statistics from Msty database"""
    total_conversations: int = 0
    total_messages: int = 0
    total_personas: int = 0
    total_prompts: int = 0
    total_knowledge_stacks: int = 0
    total_tools: int = 0
    database_size_mb: float = 0.0
    last_activity: Optional[str] = None


# =============================================================================
# Path Resolution Utilities
# =============================================================================

def get_msty_paths() -> dict:
    """Get all relevant Msty Studio paths for macOS"""
    home = Path.home()
    
    paths = {
        "app": Path("/Applications/MstyStudio.app"),
        "app_alt": Path("/Applications/Msty Studio.app"),
        "data": home / "Library/Application Support/MstyStudio",
        "sidecar": home / "Library/Application Support/MstySidecar",
        "legacy_app": Path("/Applications/Msty.app"),
        "legacy_data": home / "Library/Application Support/Msty",
    }
    
    # Resolve actual paths
    resolved = {}
    for key, path in paths.items():
        resolved[key] = str(path) if path.exists() else None
    
    # Find database
    if resolved["data"]:
        db_path = Path(resolved["data"]) / "msty.db"
        resolved["database"] = str(db_path) if db_path.exists() else None
        
        mlx_path = Path(resolved["data"]) / "models-mlx"
        resolved["mlx_models"] = str(mlx_path) if mlx_path.exists() else None
    else:
        resolved["database"] = None
        resolved["mlx_models"] = None
    
    # Check sidecar token
    if resolved["sidecar"]:
        token_path = Path(resolved["sidecar"]) / ".token"
        resolved["sidecar_token"] = str(token_path) if token_path.exists() else None
    else:
        resolved["sidecar_token"] = None
    
    return resolved


def is_process_running(process_name: str) -> bool:
    """Check if a process is running by name"""
    for proc in psutil.process_iter(['name']):
        try:
            if process_name.lower() in proc.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


# =============================================================================
# Database Operations
# =============================================================================

def get_database_connection(db_path: str) -> Optional[sqlite3.Connection]:
    """Get a read-only connection to Msty database"""
    if not db_path or not Path(db_path).exists():
        return None
    
    try:
        # Connect in read-only mode
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        return None


def query_database(db_path: str, query: str, params: tuple = ()) -> list:
    """Execute a read-only query on the Msty database"""
    conn = get_database_connection(db_path)
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        return results
    except sqlite3.Error as e:
        logger.error(f"Query error: {e}")
        return []
    finally:
        conn.close()


def get_table_names(db_path: str) -> list:
    """Get all table names from the database"""
    query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    results = query_database(db_path, query)
    return [r['name'] for r in results]


def get_table_row_count(db_path: str, table_name: str) -> int:
    """Get row count for a specific table"""
    # Sanitize table name to prevent SQL injection
    if not table_name.isidentifier():
        return 0
    query = f"SELECT COUNT(*) as count FROM {table_name}"
    results = query_database(db_path, query)
    return results[0]['count'] if results else 0


# =============================================================================
# MCP Tools - Phase 1: Foundational (Read-Only)
# =============================================================================

@mcp.tool()
def detect_msty_installation() -> str:
    """
    Detect and analyse Msty Studio Desktop installation.
    
    Returns comprehensive information about:
    - Installation status and paths
    - Application version (if detectable)
    - Running status of Msty Studio and Sidecar
    - Platform information
    - Data directory locations
    
    This is the first tool to run when working with Msty Admin MCP.
    """
    paths = get_msty_paths()
    
    # Determine if installed
    app_path = paths.get("app") or paths.get("app_alt")
    installed = app_path is not None
    
    # Get version from Info.plist if possible
    version = None
    if app_path:
        plist_path = Path(app_path) / "Contents/Info.plist"
        if plist_path.exists():
            try:
                import plistlib
                with open(plist_path, 'rb') as f:
                    plist = plistlib.load(f)
                    version = plist.get('CFBundleShortVersionString', 
                                       plist.get('CFBundleVersion'))
            except Exception as e:
                logger.warning(f"Could not read version: {e}")
    
    # Check running status
    msty_running = is_process_running("MstyStudio") or is_process_running("Msty Studio")
    sidecar_running = is_process_running("MstySidecar")
    
    # Platform info
    platform_info = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "is_apple_silicon": platform.machine() in ["arm64", "aarch64"],
        "python_version": platform.python_version()
    }
    
    installation = MstyInstallation(
        installed=installed,
        version=version,
        app_path=app_path,
        data_path=paths.get("data"),
        sidecar_path=paths.get("sidecar"),
        database_path=paths.get("database"),
        mlx_models_path=paths.get("mlx_models"),
        is_running=msty_running,
        sidecar_running=sidecar_running,
        platform_info=platform_info
    )
    
    return json.dumps(asdict(installation), indent=2)


@mcp.tool()
def read_msty_database(
    query_type: str = "stats",
    table_name: Optional[str] = None,
    limit: int = 50
) -> str:
    """
    Query the Msty Studio database for insights.
    
    Args:
        query_type: Type of query to run:
            - "stats": Get overall database statistics
            - "tables": List all tables in the database
            - "conversations": Get recent conversations
            - "personas": List configured personas
            - "prompts": List saved prompts
            - "tools": List configured MCP tools
            - "custom": Query a specific table (requires table_name)
        table_name: Table name for custom queries (only used with query_type="custom")
        limit: Maximum number of results to return (default: 50)
    
    Returns:
        JSON string with query results
    """
    paths = get_msty_paths()
    db_path = paths.get("database")
    
    if not db_path:
        return json.dumps({
            "error": "Msty database not found",
            "suggestion": "Ensure Msty Studio Desktop is installed and has been run at least once"
        })
    
    result = {"query_type": query_type, "database_path": db_path}
    
    try:
        if query_type == "tables":
            tables = get_table_names(db_path)
            table_info = []
            for table in tables:
                count = get_table_row_count(db_path, table)
                table_info.append({"name": table, "row_count": count})
            result["tables"] = table_info
            
        elif query_type == "stats":
            tables = get_table_names(db_path)
            stats = DatabaseStats()
            
            # Map common table names to stats
            table_mapping = {
                "chat_sessions": "total_conversations",
                "conversations": "total_conversations",
                "messages": "total_messages",
                "chat_messages": "total_messages",
                "personas": "total_personas",
                "prompts": "total_prompts",
                "knowledge_stacks": "total_knowledge_stacks",
                "tools": "total_tools",
                "mcp_tools": "total_tools"
            }
            
            for table in tables:
                table_lower = table.lower()
                for pattern, attr in table_mapping.items():
                    if pattern in table_lower:
                        count = get_table_row_count(db_path, table)
                        current = getattr(stats, attr, 0)
                        setattr(stats, attr, current + count)
                        break
            
            # Get database file size
            db_file = Path(db_path)
            stats.database_size_mb = round(db_file.stat().st_size / (1024 * 1024), 2)
            
            result["stats"] = asdict(stats)
            result["available_tables"] = tables
            
        elif query_type == "conversations":
            # Try common table names for conversations
            for table in ["chat_sessions", "conversations", "chat_session_folders"]:
                if table in get_table_names(db_path):
                    query = f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?"
                    result["conversations"] = query_database(db_path, query, (limit,))
                    result["source_table"] = table
                    break
            else:
                result["error"] = "No conversation table found"
                
        elif query_type == "personas":
            for table in ["personas", "persona"]:
                if table in get_table_names(db_path):
                    query = f"SELECT * FROM {table} LIMIT ?"
                    result["personas"] = query_database(db_path, query, (limit,))
                    result["source_table"] = table
                    break
            else:
                result["error"] = "No personas table found"
                
        elif query_type == "prompts":
            for table in ["prompts", "prompt_library", "saved_prompts"]:
                if table in get_table_names(db_path):
                    query = f"SELECT * FROM {table} LIMIT ?"
                    result["prompts"] = query_database(db_path, query, (limit,))
                    result["source_table"] = table
                    break
            else:
                result["error"] = "No prompts table found"
                
        elif query_type == "tools":
            for table in ["tools", "mcp_tools", "toolbox"]:
                if table in get_table_names(db_path):
                    query = f"SELECT * FROM {table} LIMIT ?"
                    result["tools"] = query_database(db_path, query, (limit,))
                    result["source_table"] = table
                    break
            else:
                result["error"] = "No tools table found"
                
        elif query_type == "custom":
            if not table_name:
                result["error"] = "table_name required for custom queries"
            elif table_name not in get_table_names(db_path):
                result["error"] = f"Table '{table_name}' not found"
                result["available_tables"] = get_table_names(db_path)
            else:
                query = f"SELECT * FROM {table_name} LIMIT ?"
                result["data"] = query_database(db_path, query, (limit,))
                result["source_table"] = table_name
        else:
            result["error"] = f"Unknown query_type: {query_type}"
            result["valid_types"] = ["stats", "tables", "conversations", "personas", "prompts", "tools", "custom"]
            
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Database query error: {e}")
    
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def list_configured_tools() -> str:
    """
    List all MCP tools configured in Msty Studio's Toolbox.
    
    Returns detailed information about each tool including:
    - Tool ID and name
    - Configuration (command, args, env vars)
    - Status and notes
    
    This helps understand what integrations are available in Msty
    and assists with Claude Desktop sync operations.
    """
    paths = get_msty_paths()
    db_path = paths.get("database")
    
    if not db_path:
        return json.dumps({
            "error": "Msty database not found",
            "tools": []
        })
    
    result = {
        "database_path": db_path,
        "tools": [],
        "tool_count": 0
    }
    
    # Try to find tools in various possible table structures
    tables = get_table_names(db_path)
    tool_tables = [t for t in tables if any(x in t.lower() for x in ["tool", "mcp"])]
    
    for table in tool_tables:
        query = f"SELECT * FROM {table}"
        tools = query_database(db_path, query)
        if tools:
            result["tools"].extend(tools)
            result["source_table"] = table
            break
    
    result["tool_count"] = len(result["tools"])
    result["available_tool_tables"] = tool_tables
    
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def get_model_providers() -> str:
    """
    Get configured AI model providers in Msty Studio.
    
    Returns information about:
    - Local models (MLX, Ollama connections)
    - Remote providers (OpenAI, Anthropic, etc.)
    - Model configurations and parameters
    
    Note: API keys are NOT returned for security reasons.
    """
    paths = get_msty_paths()
    db_path = paths.get("database")
    mlx_path = paths.get("mlx_models")
    
    result = {
        "local_models": {
            "mlx_available": mlx_path is not None,
            "mlx_path": mlx_path,
            "mlx_models": []
        },
        "remote_providers": [],
        "database_providers": []
    }
    
    # List MLX models if available
    if mlx_path and Path(mlx_path).exists():
        mlx_dir = Path(mlx_path)
        for model_dir in mlx_dir.iterdir():
            if model_dir.is_dir():
                model_info = {
                    "name": model_dir.name,
                    "path": str(model_dir),
                    "size_mb": sum(f.stat().st_size for f in model_dir.rglob('*') if f.is_file()) / (1024 * 1024)
                }
                result["local_models"]["mlx_models"].append(model_info)
    
    # Query database for provider configurations
    if db_path:
        tables = get_table_names(db_path)
        provider_tables = [t for t in tables if any(x in t.lower() for x in ["provider", "model", "remote"])]
        
        for table in provider_tables:
            query = f"SELECT * FROM {table}"
            providers = query_database(db_path, query)
            if providers:
                # Sanitize - remove any API keys
                for p in providers:
                    for key in list(p.keys()):
                        if any(x in key.lower() for x in ["key", "secret", "token", "password"]):
                            p[key] = "[REDACTED]"
                result["database_providers"].extend(providers)
                result["provider_source_table"] = table
    
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def analyse_msty_health() -> str:
    """
    Perform comprehensive health analysis of Msty Studio installation.
    
    Checks:
    - Database integrity and size
    - Storage usage and available space
    - Model cache status
    - Application and Sidecar status
    - Configuration completeness
    
    Returns a health report with status and recommendations.
    """
    paths = get_msty_paths()
    
    health = MstyHealthReport(
        overall_status="unknown",
        timestamp=datetime.now().isoformat()
    )
    
    issues = []
    warnings = []
    
    # Check installation
    if not paths.get("app") and not paths.get("app_alt"):
        issues.append("Msty Studio Desktop not installed")
        health.overall_status = "critical"
        health.recommendations.append("Install Msty Studio Desktop from https://msty.ai")
        return json.dumps(asdict(health), indent=2)
    
    # Database health
    db_path = paths.get("database")
    if db_path and Path(db_path).exists():
        db_file = Path(db_path)
        db_size_mb = db_file.stat().st_size / (1024 * 1024)
        
        # Check WAL files
        wal_path = Path(f"{db_path}-wal")
        shm_path = Path(f"{db_path}-shm")
        wal_size = wal_path.stat().st_size / (1024 * 1024) if wal_path.exists() else 0
        
        health.database_status = {
            "exists": True,
            "path": db_path,
            "size_mb": round(db_size_mb, 2),
            "wal_size_mb": round(wal_size, 2),
            "has_wal": wal_path.exists(),
            "has_shm": shm_path.exists()
        }
        
        # Database size warnings
        if db_size_mb > 500:
            warnings.append(f"Database is large ({db_size_mb:.0f}MB) - consider cleanup")
        if wal_size > 100:
            warnings.append(f"WAL file is large ({wal_size:.0f}MB) - consider VACUUM")
            health.recommendations.append("Run database optimization: sqlite3 msty.db 'PRAGMA wal_checkpoint(FULL);'")
        
        # Test database integrity
        try:
            conn = get_database_connection(db_path)
            if conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA integrity_check")
                integrity = cursor.fetchone()[0]
                health.database_status["integrity"] = integrity
                if integrity != "ok":
                    issues.append(f"Database integrity issue: {integrity}")
                conn.close()
        except Exception as e:
            health.database_status["integrity_error"] = str(e)
            warnings.append(f"Could not check database integrity: {e}")
    else:
        health.database_status = {"exists": False}
        warnings.append("Database not found - Msty may not have been run yet")
    
    # Storage health
    data_path = paths.get("data")
    if data_path:
        data_dir = Path(data_path)
        try:
            total_size = sum(f.stat().st_size for f in data_dir.rglob('*') if f.is_file())
            disk_usage = psutil.disk_usage(str(data_dir))
            
            health.storage_status = {
                "data_directory": data_path,
                "data_size_mb": round(total_size / (1024 * 1024), 2),
                "disk_total_gb": round(disk_usage.total / (1024 ** 3), 1),
                "disk_free_gb": round(disk_usage.free / (1024 ** 3), 1),
                "disk_percent_used": disk_usage.percent
            }
            
            if disk_usage.percent > 90:
                issues.append(f"Disk space critically low ({disk_usage.percent}% used)")
            elif disk_usage.percent > 80:
                warnings.append(f"Disk space getting low ({disk_usage.percent}% used)")
                
        except Exception as e:
            health.storage_status = {"error": str(e)}
    
    # Model cache health
    mlx_path = paths.get("mlx_models")
    if mlx_path and Path(mlx_path).exists():
        mlx_dir = Path(mlx_path)
        model_count = len([d for d in mlx_dir.iterdir() if d.is_dir()])
        total_size = sum(f.stat().st_size for f in mlx_dir.rglob('*') if f.is_file())
        
        health.model_cache_status = {
            "mlx_path": mlx_path,
            "model_count": model_count,
            "total_size_gb": round(total_size / (1024 ** 3), 2)
        }
        
        if total_size > 100 * (1024 ** 3):  # > 100GB
            warnings.append(f"Large model cache ({total_size / (1024**3):.1f}GB) - consider cleanup")
    else:
        health.model_cache_status = {"mlx_available": False}
    
    # Process status
    msty_running = is_process_running("MstyStudio") or is_process_running("Msty Studio")
    sidecar_running = is_process_running("MstySidecar")
    
    health.recommendations.extend([
        f"Msty Studio: {'Running ✅' if msty_running else 'Not running'}",
        f"Sidecar: {'Running ✅' if sidecar_running else 'Not running - MCP tools may not work'}"
    ])
    
    if not sidecar_running:
        health.recommendations.append("Start Sidecar: open -a MstySidecar (from Terminal for best dependency detection)")
    
    # Determine overall status
    if issues:
        health.overall_status = "critical"
        health.recommendations = [f"❌ {i}" for i in issues] + health.recommendations
    elif warnings:
        health.overall_status = "warning"
        health.recommendations = [f"⚠️ {w}" for w in warnings] + health.recommendations
    else:
        health.overall_status = "healthy"
        health.recommendations.insert(0, "✅ Msty Studio installation is healthy")
    
    return json.dumps(asdict(health), indent=2)


@mcp.tool()
def get_server_status() -> str:
    """
    Get the current status of the Msty Admin MCP server.
    
    Returns server information including:
    - Server name and version
    - Available tools
    - Msty installation status summary
    - Current capabilities
    """
    paths = get_msty_paths()
    
    status = {
        "server": {
            "name": "msty-admin-mcp",
            "version": "2.0.0",
            "phase": "Phase 1 - Foundational (Read-Only)",
            "author": "Pineapple 🍍"
        },
        "available_tools": [
            "detect_msty_installation",
            "read_msty_database",
            "list_configured_tools",
            "get_model_providers",
            "analyse_msty_health",
            "get_server_status"
        ],
        "msty_status": {
            "installed": paths.get("app") is not None or paths.get("app_alt") is not None,
            "database_available": paths.get("database") is not None,
            "sidecar_configured": paths.get("sidecar") is not None,
            "mlx_models_available": paths.get("mlx_models") is not None
        },
        "planned_phases": {
            "phase_2": "Configuration Management (export_tool_config, generate_persona, sync_claude_preferences)",
            "phase_3": "Automation Bridge (open_msty_studio, trigger_toolbox_import, backup/restore)",
            "phase_4": "Intelligence Layer (model recommendations, conversation analytics, optimization)"
        }
    }
    
    return json.dumps(status, indent=2)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Run the Msty Admin MCP server"""
    logger.info("Starting Msty Admin MCP Server v2.0.0")
    logger.info("Phase 1: Foundational Tools (Read-Only)")
    mcp.run()


if __name__ == "__main__":
    main()
