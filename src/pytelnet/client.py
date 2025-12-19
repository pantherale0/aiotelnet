"""Connect to a Telnet server and interact with it."""

import logging

import asyncio
from typing import Callable

_LOGGER = logging.getLogger(__name__)


class TelnetClient:
    """Asynchronous Telnet client for connecting and interacting with a Telnet server.

    This client provides a non-blocking interface for Telnet communication with features
    like automatic reconnection, custom message handling, and configurable encoding.
    """

    def __init__(
        self,
        host: str,
        port: int = 23,
        message_handler: Callable | None = None,  # type: ignore
        break_line: bytes = b"\n",
        command_prefix: str = "",
        command_suffix: str = "",
        encoding: str = "utf-8",
        auto_reconnect: bool = True,
        reconnect_interval: int = 10,
        timeout: int = 10,
    ):
        """Initialize a TelnetClient instance.

        Args:
            host: The hostname or IP address of the Telnet server.
            port: The port number to connect to (default: 23, standard Telnet port).
            message_handler: Optional callable to handle incoming messages. Can be either
                a synchronous function or an async coroutine that accepts bytes.
                Signature: (message: bytes) -> None or Awaitable[None]
            break_line: The byte sequence that separates messages (default: b'\\n').
                Used to determine message boundaries when reading from the server.
            command_prefix: A string to prepend to every command sent to the server
                (default: ''). Useful for adding protocol-specific prefixes.
            command_suffix: A string to append to every command sent to the server
                (default: ''). Useful for adding protocol-specific suffixes like newlines.
            encoding: The character encoding to use for command strings (default: 'utf-8').
                Used when encoding commands to bytes before sending.
            auto_reconnect: Whether to automatically reconnect if the connection is lost
                (default: True). When enabled, a background task will attempt reconnection.
            reconnect_interval: The interval in seconds between reconnection attempts
                (default: 10). Applied both during connection loss and between retries.
            timeout: The timeout in seconds for establishing a connection (default: 10).
                Used to prevent indefinite hanging on connection attempts.
        """
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
        self.command_prefix = command_prefix
        self.command_suffix = command_suffix
        self._is_connected = False

    async def connect(self) -> None:
        """Establish a connection to the Telnet server.

        Initiates a connection to the Telnet server at the configured host and port.
        If already connected, this method returns immediately without attempting
        to reconnect.

        On successful connection:
        - Starts the listener task to receive messages from the server
        - Starts the reconnect task if auto_reconnect is enabled
        - Updates internal connection state

        Raises:
            ConnectionError: If the connection fails due to network errors, timeout,
                or inability to reach the server.

        Note:
            This is an async method and must be called with await.
            The connection timeout is configurable via the timeout parameter.
        """
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
        """Check if the client is currently connected to the server.

        Returns:
            bool: True if the client is connected and the writer is not closing,
                False otherwise.

        Note:
            This method checks both the internal connection state and the
            underlying writer's closing status to ensure accuracy.
        """
        return self._is_connected and self.writer is not None and not self.writer.is_closing()

    async def send_command(self, command: str) -> None:
        """Send a command to the Telnet server.

        Encodes the command using the configured encoding and sends it to the server.
        The command_prefix and command_suffix are automatically prepended and appended
        to the command before transmission.

        The final command format is: prefix + command + suffix

        Args:
            command: The command string to send to the Telnet server.

        Raises:
            ConnectionError: If the client is not currently connected to the server.

        Note:
            - To receive responses from the server, a message_handler must be
              provided when initializing the client.
            - The command is automatically encoded using the configured encoding.
            - The configured command_prefix and command_suffix are automatically
              applied to every command sent (set these during initialization).
            - This method will wait until the data is flushed to the server.

        Example:
            # Without prefix/suffix:
            client = TelnetClient('localhost', 23)
            await client.send_command('hello')

            # With prefix and suffix:
            client = TelnetClient('localhost', 23, command_prefix='>', command_suffix='\\n')
            await client.send_command('hello')  # Sends: '>hello\\n'
        """
        _LOGGER.debug("Sending command to Telnet server %s:%s - %s", self.host, self.port, command)
        if self.writer is None or self.reader is None:
            raise ConnectionError("Not connected to the server.")
        command = f"{self.command_prefix}{command}{self.command_suffix}"
        self.writer.write(command.encode(self.encoding))
        await self.writer.drain()

    async def close(self) -> None:
        """Close the connection to the Telnet server.

        Gracefully closes the Telnet connection by:
        - Setting the connection state to closed
        - Disabling automatic reconnection to prevent reconnect attempts
        - Cancelling the reconnect task if running
        - Cancelling the listener task if running
        - Closing the writer and waiting for it to fully close
        - Clearing reader and writer references

        Note:
            - This method is safe to call multiple times
            - All background tasks are properly cancelled and awaited
            - No exceptions are raised if the connection is already closed
            - This is an async method and must be called with await

        Example:
            await client.close()
        """
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

    async def _reconnect_task(self) -> None:
        """Background task that handles automatic reconnection to the Telnet server.

        This is an internal method that runs continuously as a background task when
        auto_reconnect is enabled. It monitors the connection state and attempts
        to reconnect if the connection is lost.

        Behavior:
        - Waits for the configured reconnect_interval before checking connection status
        - Attempts to reconnect if the connection is detected as lost
        - Catches and logs ConnectionError exceptions without stopping the task
        - Sleeps between reconnection attempts to avoid excessive CPU usage
        - Can be cancelled via asyncio.CancelledError (handled internally)

        Note:
            - This task is automatically created and managed by the connect() method
            - Should not be called directly by users
            - Exceptions are logged but not raised to prevent task termination
            - The task runs indefinitely until cancelled by close()
        """
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

    async def _listener_task(self) -> None:
        """Background task that continuously listens for incoming messages from the server.

        This is an internal method that runs continuously as a background task after
        a successful connection. It reads messages from the server and dispatches them
        to the configured message_handler.

        Behavior:
        - Waits for the configured break_line sequence to identify message boundaries
        - Calls the message_handler (if configured) with each received message
        - Supports both synchronous and asynchronous message handlers
        - Handles connection drops and errors gracefully
        - Clears connection state when disconnected, triggering reconnection logic
        - Stops listening if auto_reconnect is disabled after a disconnection

        Error Handling:
        - asyncio.IncompleteReadError: Connection closed unexpectedly, clears reader/writer
        - ConnectionResetError: Server forcibly closed connection, clears reader/writer
        - asyncio.CancelledError: Task was explicitly cancelled, breaks the loop cleanly

        Note:
            - This task is automatically created and managed by the connect() method
            - Should not be called directly by users
            - If message_handler is None, messages are silently discarded
            - Exceptions in the message_handler may cause task termination
            - The task runs indefinitely until cancelled or connection is lost
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
