# aiotelnet: Async Telnet Client

aiotelnet is a lightweight, asynchronous Telnet client for Python, designed for easy integration into modern async applications.

Notice: AI has been used to generate parts of this project. It has been checked against Python documentation for correctness.

This project was born due to the lack of standard async telnet library, while it has been built primarily for telnet usage, it could also be used for any kind of low-level server/client network communication.

## Features

- **Asynchronous:** Built on `asyncio` for non-blocking network I/O.
- **Automatic Reconnection:** Can automatically reconnect to the server if the connection is lost.
- **Easy to Use:** Simple and intuitive API for connecting, sending commands, and handling messages.
- **Customizable:** Allows customization of encoding, line breaks, and reconnection behavior.

## Installation

```bash
pip install aiotelnet
```

## Usage

Here's a basic example of how to use `TelnetClient` to connect to a Telnet server, send a command, and receive messages:

```python
import asyncio

from aiotelnet.client import TelnetClient


# Define a message handler
async def message_handler(message: bytes):
    """Handle incoming messages from the Telnet server."""
    print(f"Received: {message.decode('utf-8').strip()}")


async def main():
    """Connect to the Telnet server and send a command."""
    # Create a Telnet client
    client = TelnetClient(
        host="telehack.com",
        port=23,
        message_handler=message_handler,
    )

    try:
        # Establish the connection
        await client.connect()

        # Send a command
        await client.send_command("hello")

        # Keep the connection open for a while
        await asyncio.sleep(10)

    except ConnectionError as e:
        print(f"Connection failed: {e}")
    finally:
        # Close the connection
        if client.is_connected():
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

## API Reference

### `TelnetClient(host, port, message_handler, ...)`

- `host`: The Telnet server host.
- `port`: The Telnet server port (default: 23).
- `message_handler`: An optional callable (sync or async) to handle incoming messages.
- `break_line`: The byte sequence that separates messages (default: `b'\\n'`).
- `encoding`: The encoding to use for commands (default: `'utf-8'`).
- `auto_reconnect`: Whether to automatically reconnect if the connection is lost (default: `True`).
- `reconnect_interval`: The interval in seconds between reconnection attempts (default: `10`).

### `async connect()`

Establishes a connection to the Telnet server.

### `is_connected() -> bool`

Returns `True` if the client is connected, `False` otherwise.

### `async send_command(command: str)`

Sends a command to the Telnet server.

### `async close()`

Closes the connection to the Telnet server.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on GitHub.

## License

This project is licensed under the Apache 2.0 License.
