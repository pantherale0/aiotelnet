"""Test the telnet client implementation."""

import asyncio
from typing import Callable
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, create_autospec

from pytelnet.client import TelnetClient


def test_module_version():
    """Test that the module version is defined."""
    from pytelnet import __version__

    assert isinstance(__version__, str)
    assert __version__ == "1.0.0"  # This is overridden during release process


@pytest.mark.asyncio
async def test_telnet_client_connect_and_close(telnet_client_factory: Callable[..., TelnetClient]):
    """Test connecting and closing a TelnetClient."""
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
        assert client.is_connected() is True
        mock_open_connection.assert_called_with("localhost", 12345)

        await client.close()
        assert client.is_connected() is False
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_telnet_client_send_command(telnet_client_factory: Callable[..., TelnetClient]):
    """Test sending a command with TelnetClient."""
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
        await client.send_command("test command")

        mock_writer.write.assert_called_with(b"test command")
        mock_writer.drain.assert_awaited_once()
        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_message_handler(telnet_client_factory: Callable[..., TelnetClient]):
    """Test the message handler of TelnetClient."""
    mock_message_handler = MagicMock()
    client = telnet_client_factory(
        host="localhost",
        port=12345,
        message_handler=mock_message_handler,
        auto_reconnect=False,
    )

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_connection:
        mock_reader = AsyncMock()
        mock_reader.readuntil.side_effect = [b"hello\n", asyncio.CancelledError()]
        mock_writer = create_autospec(asyncio.StreamWriter, instance=True)
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_reader, mock_writer)

        await client.connect()
        await asyncio.sleep(0.1)  # allow listener task to run

        mock_message_handler.assert_called_with(b"hello\n")
        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_async_message_handler(telnet_client_factory: Callable[..., TelnetClient]):
    """Test the message handler of TelnetClient with an async handler."""
    mock_message_handler = AsyncMock()
    client = telnet_client_factory(
        host="localhost",
        port=12345,
        message_handler=mock_message_handler,
        auto_reconnect=False,
    )

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_connection:
        mock_reader = AsyncMock()
        mock_reader.readuntil.side_effect = [
            b"hello async\n",
            asyncio.CancelledError(),
        ]
        mock_writer = create_autospec(asyncio.StreamWriter, instance=True)
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_reader, mock_writer)

        await client.connect()
        await asyncio.sleep(0.1)  # allow listener task to run

        mock_message_handler.assert_called_with(b"hello async\n")
        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_connection_error(telnet_client_factory: Callable[..., TelnetClient]):
    """Test ConnectionError during connection."""
    client = telnet_client_factory(host="localhost", port=12345, auto_reconnect=False)

    with patch("asyncio.open_connection", side_effect=OSError("Connection failed")) as mock_open_connection:
        with pytest.raises(ConnectionError):
            await client.connect()
        mock_open_connection.assert_called_with("localhost", 12345)


@pytest.mark.asyncio
async def test_telnet_client_send_command_not_connected(
    disconnected_telnet_client: TelnetClient,
):
    """Test sending command when not connected."""
    with pytest.raises(ConnectionError):
        await disconnected_telnet_client.send_command("test")


@pytest.mark.asyncio
async def test_telnet_client_auto_reconnect(telnet_client_factory: Callable[..., TelnetClient]):
    """Test the auto-reconnect functionality."""
    client = telnet_client_factory(host="localhost", port=12345, reconnect_interval=0.1, auto_reconnect=True)

    mock_reader_1 = AsyncMock()
    mock_reader_1.readuntil.side_effect = ConnectionResetError()
    mock_writer_1 = create_autospec(asyncio.StreamWriter, instance=True)
    mock_writer_1.is_closing.return_value = False
    mock_writer_1.drain = AsyncMock()
    mock_writer_1.wait_closed = AsyncMock()

    mock_reader_2 = AsyncMock()
    mock_reader_2.readuntil.side_effect = asyncio.CancelledError()
    mock_writer_2 = create_autospec(asyncio.StreamWriter, instance=True)
    mock_writer_2.is_closing.return_value = False
    mock_writer_2.drain = AsyncMock()
    mock_writer_2.wait_closed = AsyncMock()

    # First connection succeeds, then we'll simulate a disconnect
    mock_open_connection = AsyncMock(
        side_effect=[
            (mock_reader_1, mock_writer_1),
            (mock_reader_2, mock_writer_2),
        ]
    )

    with patch("asyncio.open_connection", mock_open_connection):
        await client.connect()
        assert client.is_connected() is True
        assert mock_open_connection.call_count == 1

        # Simulate disconnection
        mock_reader_1.readuntil.side_effect = ConnectionResetError()
        await asyncio.sleep(0.2)  # give time for listener to process disconnection and reconnect task to run

        # It should reconnect again
        assert client.is_connected() is True
        assert mock_open_connection.call_count == 2

        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_no_connect_if_already_connected(
    connected_telnet_client: TelnetClient,
):
    """Test that connect does not reconnect if already connected."""
    client = connected_telnet_client

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_connection:
        await client.connect()
        mock_open_connection.assert_not_called()


@pytest.mark.asyncio
async def test_telnet_client_close_cancels_listener_task(telnet_client_factory):
    client = telnet_client_factory(host="localhost", port=12345, auto_reconnect=False)
    # Mock writer
    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    client.writer = mock_writer

    # Create a real task that will be cancelled (long-running)
    async def long_running_task():
        try:
            await asyncio.sleep(10)  # Long sleep that will be cancelled
        except asyncio.CancelledError:
            raise  # Re-raise to propagate the cancellation

    listener_task = asyncio.create_task(long_running_task())
    client.listener_task = listener_task

    await client.close()

    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_awaited_once()
    assert client.listener_task is None


@pytest.mark.asyncio
async def test_telnet_client_close_cancels_reconnect_task(telnet_client_factory):
    """Test that close cancels the reconnect task."""
    client = telnet_client_factory(host="localhost", port=12345, auto_reconnect=True)
    # Mock writer
    mock_writer = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    client.writer = mock_writer

    # Create a real task that will be cancelled
    async def long_running_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise

    reconnect_task = asyncio.create_task(long_running_task())
    client.reconnect_task = reconnect_task

    await client.close()

    mock_writer.close.assert_called_once()
    mock_writer.wait_closed.assert_awaited_once()
    assert client.reconnect_task is None
    assert client.auto_reconnect is False


@pytest.mark.asyncio
async def test_telnet_client_listener_task_incomplete_read_error(telnet_client_factory: Callable[..., TelnetClient]):
    """Test listener task handling asyncio.IncompleteReadError."""
    client = telnet_client_factory(host="localhost", port=12345, auto_reconnect=False)

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_connection:
        mock_reader = AsyncMock()
        mock_reader.readuntil.side_effect = [
            asyncio.IncompleteReadError(b"partial", 10),
        ]
        mock_writer = create_autospec(asyncio.StreamWriter, instance=True)
        mock_writer.is_closing.return_value = False
        mock_writer.close = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_reader, mock_writer)

        await client.connect()
        await asyncio.sleep(0.1)  # allow listener task to process error

        assert client.reader is None
        assert client.writer is None
        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_listener_task_reader_none(telnet_client_factory: Callable[..., TelnetClient]):
    """Test listener task handles reader being None."""
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
        # Clear reader to test the None check in listener task
        client.reader = None
        await asyncio.sleep(0.1)

        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_reconnect_task_connection_error_retry(telnet_client_factory: Callable[..., TelnetClient]):
    """Test reconnect task retries on ConnectionError during listener operation."""
    client = telnet_client_factory(host="localhost", port=12345, reconnect_interval=0.05, auto_reconnect=True)

    # First setup a successful connection
    mock_reader_1 = AsyncMock()
    mock_reader_1.readuntil.side_effect = ConnectionResetError()
    mock_writer_1 = create_autospec(asyncio.StreamWriter, instance=True)
    mock_writer_1.is_closing.return_value = False
    mock_writer_1.drain = AsyncMock()
    mock_writer_1.wait_closed = AsyncMock()

    # Second connection after reconnect
    mock_reader_2 = AsyncMock()
    mock_reader_2.readuntil.side_effect = asyncio.CancelledError()
    mock_writer_2 = create_autospec(asyncio.StreamWriter, instance=True)
    mock_writer_2.is_closing.return_value = False
    mock_writer_2.drain = AsyncMock()
    mock_writer_2.wait_closed = AsyncMock()

    mock_open_connection = AsyncMock(
        side_effect=[
            (mock_reader_1, mock_writer_1),
            (mock_reader_2, mock_writer_2),
        ]
    )

    with patch("asyncio.open_connection", mock_open_connection):
        await client.connect()
        assert client.is_connected() is True

        # Simulate disconnection
        await asyncio.sleep(0.15)  # give time for listener to detect disconnection and reconnect

        # It should have reconnected
        assert client.is_connected() is True
        assert mock_open_connection.call_count == 2

        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_listener_task_no_message_handler(telnet_client_factory: Callable[..., TelnetClient]):
    """Test listener task with no message handler."""
    client = telnet_client_factory(host="localhost", port=12345, message_handler=None, auto_reconnect=False)

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_connection:
        mock_reader = AsyncMock()
        mock_reader.readuntil.side_effect = [b"test\n", asyncio.CancelledError()]
        mock_writer = create_autospec(asyncio.StreamWriter, instance=True)
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_reader, mock_writer)

        await client.connect()
        await asyncio.sleep(0.1)  # allow listener task to process message

        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_listener_task_no_auto_reconnect_on_disconnect(
    telnet_client_factory: Callable[..., TelnetClient],
):
    """Test listener task breaks when disconnected with auto_reconnect disabled."""
    client = telnet_client_factory(host="localhost", port=12345, auto_reconnect=False)

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open_connection:
        mock_reader = AsyncMock()
        # Raise ConnectionResetError to trigger the break in listener task
        mock_reader.readuntil.side_effect = ConnectionResetError()
        mock_writer = create_autospec(asyncio.StreamWriter, instance=True)
        mock_writer.is_closing.return_value = False
        mock_writer.close = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()
        mock_open_connection.return_value = (mock_reader, mock_writer)

        await client.connect()
        assert client.is_connected() is True
        assert client.listener_task is not None

        # Wait for listener task to encounter the error and break
        await asyncio.sleep(0.1)

        # Verify listener task has exited (done) and reader is cleared
        assert client.listener_task.done()
        assert client.reader is None
        await client.close()


@pytest.mark.asyncio
async def test_telnet_client_reconnect_connection_error_caught(telnet_client_factory: Callable[..., TelnetClient]):
    """Test reconnect task catches ConnectionError and continues."""
    client = telnet_client_factory(host="localhost", port=12345, reconnect_interval=0.05, auto_reconnect=True)

    call_count = 0

    async def mock_open_connection_side_effect(host, port):
        nonlocal call_count
        call_count += 1
        # First call succeeds, second call (reconnect after disconnect) fails, third succeeds
        if call_count == 1:
            mock_reader = AsyncMock()
            mock_reader.readuntil.side_effect = ConnectionResetError()
            mock_writer = create_autospec(asyncio.StreamWriter, instance=True)
            mock_writer.is_closing.return_value = False
            mock_writer.close = MagicMock()
            mock_writer.drain = AsyncMock()
            mock_writer.wait_closed = AsyncMock()
            return (mock_reader, mock_writer)
        elif call_count == 2:
            raise OSError("Reconnect failed")
        else:
            mock_reader = AsyncMock()
            mock_reader.readuntil.side_effect = asyncio.CancelledError()
            mock_writer = create_autospec(asyncio.StreamWriter, instance=True)
            mock_writer.is_closing.return_value = False
            mock_writer.drain = AsyncMock()
            mock_writer.wait_closed = AsyncMock()
            return (mock_reader, mock_writer)

    with patch("asyncio.open_connection", side_effect=mock_open_connection_side_effect):
        await client.connect()
        assert client.is_connected() is True
        initial_call_count = call_count

        # Wait for listener to detect disconnect and trigger reconnect attempts
        await asyncio.sleep(0.3)

        # Should have attempted reconnect (multiple calls)
        assert call_count > initial_call_count

        await client.close()
