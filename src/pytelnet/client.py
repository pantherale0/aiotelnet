"""Connect to a Telnet server and interact with it."""

import logging

import asyncio
from typing import Callable

_LOGGER = logging.getLogger(__name__)


class TelnetClient:
    """Telnet client for connecting and interacting with a Telnet server."""

    def __init__(
        self,
        host: str,
        port: int = 23,
        message_handler: Callable | None = None,  # type: ignore
        break_line: bytes = b"\n",
        encoding: str = "utf-8",
        auto_reconnect: bool = True,
        reconnect_interval: int = 10,
        timeout: int = 10,
    ):
        self.host: str = host
        self.port = port
        self.reader = None
        self.writer = None
        self.reconnect_task = None
        self.listener_task = None
        self.message_handler: Callable | None = message_handler  # type: ignore
        self.break_line = break_line
        self.reconnect_interval = reconnect_interval
        self.encoding = encoding
        self.auto_reconnect = auto_reconnect
        self.timeout = timeout
        self._is_connected = False

    async def connect(self):
        """Establish a connection to the Telnet server."""
        _LOGGER.debug("Connecting to Telnet server at %s:%s", self.host, self.port)
        if self.is_connected():
            return
        connection = asyncio.open_connection(self.host, self.port)
        try:
            self.reader, self.writer = await asyncio.wait_for(connection, timeout=self.timeout)
            if self.listener_task is None or self.listener_task.done():
                self.listener_task = asyncio.create_task(self._listener_task())

            if self.auto_reconnect and (self.reconnect_task is None or self.reconnect_task.done()):
                self.reconnect_task = asyncio.create_task(self._reconnect_task())
            self._is_connected = True
        except (OSError, asyncio.TimeoutError) as e:
            self._is_connected = False
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}") from e

    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._is_connected and self.writer is not None and not self.writer.is_closing()

    async def send_command(self, command: str):
        """Send a command to the Telnet server. To receive responses, a message_handler must be provided."""
        _LOGGER.debug("Sending command to Telnet server %s:%s - %s", self.host, self.port, command)
        if self.writer is None or self.reader is None:
            raise ConnectionError("Not connected to the server.")

        self.writer.write(command.encode(self.encoding) + b"\n")
        await self.writer.drain()

    async def close(self):
        """Close the connection to the Telnet server."""
        _LOGGER.debug("Closing connection to Telnet server at %s:%s", self.host, self.port)
        self._is_connected = False
        self.auto_reconnect = False  # Prevent reconnection attempts
        if self.reconnect_task:
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass  # Task cancellation is expected
            self.reconnect_task = None
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass  # Task cancellation is expected
            self.listener_task = None
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self.writer = None
        self.reader = None

    async def _reconnect_task(self):
        """Internal method to handle automatic reconnection to the telnet server."""
        await asyncio.sleep(self.reconnect_interval)  # Initial delay
        while True:
            if not self.is_connected():
                _LOGGER.debug("Reconnecting to Telnet server at %s:%s", self.host, self.port)
                try:
                    await self.connect()
                except ConnectionError:
                    # Connection failed, will retry after interval
                    _LOGGER.exception("Reconnection to Telnet server at %s:%s failed", self.host, self.port)
                    pass
                except asyncio.CancelledError:
                    _LOGGER.debug("Reconnection task cancelled for Telnet server at %s:%s", self.host, self.port)
                    break
            await asyncio.sleep(self.reconnect_interval)

    async def _listener_task(self):
        """
        Internal task that continuously listens for incoming messages from the server.

        Handles connection drops gracefully:
        - Closes the writer on connection reset
        - Clears reader reference to trigger reconnection logic
        - Breaks the loop if auto_reconnect is disabled

        Raises:
            asyncio.CancelledError: When the task is explicitly cancelled.
        """
        while True:
            if self.reader is None:
                await asyncio.sleep(0.1)
                continue

            try:
                message = await self.reader.readuntil(self.break_line)
            except (asyncio.IncompleteReadError, ConnectionResetError):
                _LOGGER.debug("Connection lost while reading from Telnet server at %s:%s", self.host, self.port)
                message = b""
                # Connection closed by server, trigger reconnect logic
                if self.writer:
                    self.writer.close()
                    self.writer = None
                self.reader = None
                if not self.auto_reconnect:
                    break
            except asyncio.CancelledError:
                _LOGGER.debug("Listener task cancelled for Telnet server at %s:%s", self.host, self.port)
                break
            else:
                _LOGGER.debug("Received message from Telnet server at %s:%s - %s", self.host, self.port, message)
                if self.message_handler:
                    # Check if the message handler is a coroutine function
                    if asyncio.iscoroutinefunction(self.message_handler):
                        await self.message_handler(message)
                    else:
                        self.message_handler(message)
