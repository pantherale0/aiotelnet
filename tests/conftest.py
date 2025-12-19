"""
This is a configuration file for pytest containing customizations and fixtures.

In VSCode, Code Coverage is recorded in config.xml. Delete this file to reset reporting.
"""

import asyncio
from typing import Callable
import pytest
from unittest.mock import AsyncMock, patch, create_autospec

from pytelnet.client import TelnetClient


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def telnet_client_factory(event_loop: asyncio.AbstractEventLoop) -> Callable[..., TelnetClient]:
    """Factory fixture to create TelnetClient instances."""

    def _factory(
        host: str,
        port: int = 23,
        message_handler: Callable | None = None,  # type: ignore
        break_line: bytes = b"\n",
        encoding: str = "utf-8",
        auto_reconnect: bool = True,
        reconnect_interval: int = 10,
    ) -> TelnetClient:
        return TelnetClient(
            host=host,
            port=port,
            message_handler=message_handler,
            break_line=break_line,
            encoding=encoding,
            auto_reconnect=auto_reconnect,
            reconnect_interval=reconnect_interval,
        )

    return _factory


@pytest.fixture
async def connected_telnet_client(telnet_client_factory):
    """Fixture providing a connected TelnetClient with mocked connection."""
    client = telnet_client_factory(host="localhost", port=12345, auto_reconnect=False)

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_connection:
        mock_reader = AsyncMock()
        mock_reader.readuntil.side_effect = asyncio.CancelledError()
        mock_writer = create_autospec(asyncio.StreamWriter, instance=True)
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_reader, mock_writer)

        await client.connect()
        yield client
        await client.close()


@pytest.fixture
async def disconnected_telnet_client(telnet_client_factory: Callable[..., TelnetClient]):
    """Fixture to provide a disconnected TelnetClient instance."""
    client = telnet_client_factory(host="localhost", port=23, auto_reconnect=False)
    yield client
    if client.is_connected():
        await client.close()


@pytest.fixture
def sample_message_handler() -> Callable[[str], None]:
    """Fixture to provide a sample message handler."""

    def _handler(message: str):
        print(f"Received message: {message}")

    return _handler
