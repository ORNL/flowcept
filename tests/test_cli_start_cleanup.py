import shutil
import socket
import subprocess
import sys
import time

import pytest

from flowcept.cli import _listener_pids, _stop_existing_start_services


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_listener(port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _listener_pids(port):
            return True
        time.sleep(0.1)
    return False


@pytest.mark.skipif(shutil.which("lsof") is None, reason="lsof is required for CLI port cleanup")
def test_start_cleanup_stops_existing_webservice_listener(capsys):
    """Unified startup reports and stops an existing listener on the requested port."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for_listener(port), "temporary listener did not start"

        _stop_existing_start_services(webservice=True, webservice_port=str(port))

        output = capsys.readouterr().out
        assert f"Stopping stale Webservice listener on port {port}" in output
        assert not _wait_for_listener(port, timeout=1.0)
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
