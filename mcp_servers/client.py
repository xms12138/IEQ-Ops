"""Synchronous in-memory MCP client wrapper (Phase 1 dev transport).

The dev transport is FastMCP in-memory — Client(server_instance), same process,
zero orchestration — but the call still goes through the real MCP protocol
(schema validation, structured output). The graph stays synchronous, so each
call wraps the async FastMCP client in asyncio.run. Phase 5 swaps the transport
(stdio / HTTP) by editing only this module; agent call sites do not change.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import Client, FastMCP


async def _acall(server: FastMCP, name: str, args: dict[str, Any]) -> Any:
    async with Client(server) as client:
        result = await client.call_tool(name, args)
        return result.data


def call_tool(server: FastMCP, name: str, /, **args: Any) -> Any:
    """Call an MCP tool synchronously and return its structured result (.data)."""
    return asyncio.run(_acall(server, name, args))
