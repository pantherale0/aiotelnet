"""Connect to a Telnet server and interact with it."""

import asyncio
from typing import Callable


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

    async def connect(self):
        """Establish a connection to the Telnet server."""
        if self.is_connected():
            return

        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            if self.listener_task is None or self.listener_task.done():
                self.listener_task = asyncio.create_task(self._listener_task())

            if self.auto_reconnect and (self.reconnect_task is None or self.reconnect_task.done()):
                self.reconnect_task = asyncio.create_task(self._reconnect_task())
        except (OSError, asyncio.TimeoutError) as e:
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}") from e

    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self.writer is not None and not self.writer.is_closing()

    async def send_command(self, command: str):
        """Send a command to the Telnet server. To receive responses, a message_handler must be provided."""
        if self.writer is None or self.reader is None:
            raise ConnectionError("Not connected to the server.")

        self.writer.write(command.encode(self.encoding) + b"\n")
        await self.writer.drain()

    async def close(self):
        """Close the connection to the Telnet server."""
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
                try:
                    await self.connect()
                except ConnectionError:
                    # Connection failed, will retry after interval
                    pass
            await asyncio.sleep(self.reconnect_interval)

    async def _listener_task(self):
        """Internal method to listen for incoming messages from the server."""
        while True:
            if self.reader is None:
                await asyncio.sleep(0.1)
                continue

            try:
                message = await self.reader.readuntil(self.break_line)
            except (asyncio.IncompleteReadError, ConnectionResetError):
                # Connection closed by server, trigger reconnect logic
                if self.writer:
                    self.writer.close()
                    self.writer = None
                self.reader = None
                if not self.auto_reconnect:
                    break
            else:
                if self.message_handler:
                    # Check if the message handler is a coroutine function
                    if asyncio.iscoroutinefunction(self.message_handler):
                        await self.message_handler(message)
                    else:
                        self.message_handler(message)
