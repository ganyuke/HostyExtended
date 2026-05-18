"""
Test the WinIPC backend by simulating what the C# PythonBackendClient does:
send JSON requests via stdin and read JSON responses via stdout.
"""
import subprocess
import sys
import json
import time
import os

# We run from the repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")
IPC_SCRIPT = os.path.join(REPO_ROOT, "hosty", "win_ipc.py")


def start_backend():
    """Start the Python IPC backend, just like the C# side does."""
    proc = subprocess.Popen(
        [PYTHON, IPC_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": REPO_ROOT},
        text=True,
        bufsize=1,  # line-buffered
    )
    return proc


def read_line(proc, timeout=10):
    """Read a single line from stdout, with a timeout."""
    import threading

    result = [None]
    error = [None]

    def _read():
        try:
            result[0] = proc.stdout.readline()
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise TimeoutError(f"Timed out after {timeout}s waiting for stdout line")

    if error[0]:
        raise error[0]

    return result[0]


def send_request(proc, req_id, method, params=None):
    """Send a JSON-RPC-style request."""
    msg = {"id": req_id, "method": method, "params": params or {}}
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()


def parse_response(line):
    """Parse a JSON line from stdout."""
    return json.loads(line.strip())


def test_ready_event():
    """Test 1: Backend should emit a 'ready' event on startup."""
    print("=== Test: ready event ===")
    proc = start_backend()
    try:
        line = read_line(proc, timeout=15)
        msg = parse_response(line)
        assert msg.get("event") == "ready", f"Expected 'ready' event, got: {msg}"
        print("  PASS: Got ready event")
    finally:
        proc.kill()
        proc.wait()


def test_ping():
    """Test 2: ping should return pong."""
    print("=== Test: ping ===")
    proc = start_backend()
    try:
        # Read and discard the 'ready' event
        ready = read_line(proc, timeout=15)
        assert '"ready"' in ready, f"Expected ready event, got: {ready}"

        send_request(proc, 1, "ping")
        line = read_line(proc, timeout=5)
        msg = parse_response(line)
        assert msg.get("id") == 1, f"Expected id=1, got: {msg}"
        assert msg.get("result") == "pong", f"Expected result='pong', got: {msg}"
        print("  PASS: ping -> pong")
    finally:
        proc.kill()
        proc.wait()


def test_get_servers():
    """Test 3: get_servers should return a list (possibly empty)."""
    print("=== Test: get_servers ===")
    proc = start_backend()
    try:
        ready = read_line(proc, timeout=15)
        assert '"ready"' in ready

        send_request(proc, 2, "get_servers")
        line = read_line(proc, timeout=5)
        msg = parse_response(line)
        assert msg.get("id") == 2, f"Expected id=2, got: {msg}"
        assert isinstance(msg.get("result"), list), f"Expected list result, got: {msg}"
        print(f"  PASS: get_servers returned {len(msg['result'])} servers")
    finally:
        proc.kill()
        proc.wait()


def test_get_versions():
    """Test 4: get_versions should return game_versions and loader_versions."""
    print("=== Test: get_versions ===")
    proc = start_backend()
    try:
        ready = read_line(proc, timeout=15)
        assert '"ready"' in ready

        send_request(proc, 3, "get_versions")
        line = read_line(proc, timeout=30)  # Network call, can be slow
        msg = parse_response(line)
        assert msg.get("id") == 3, f"Expected id=3, got: {msg}"

        if "error" in msg and msg["error"] is not None:
            print(f"  WARN: get_versions returned an error (network?): {msg['error']}")
        else:
            result = msg.get("result", {})
            game = result.get("game_versions", [])
            loader = result.get("loader_versions", [])
            assert isinstance(game, list), f"Expected list for game_versions, got: {type(game)}"
            assert isinstance(loader, list), f"Expected list for loader_versions, got: {type(loader)}"
            assert len(game) > 0, "Expected at least one game version"
            assert len(loader) > 0, "Expected at least one loader version"
            print(f"  PASS: get_versions returned {len(game)} game versions, {len(loader)} loader versions")
    finally:
        proc.kill()
        proc.wait()


def test_unknown_method():
    """Test 5: Unknown method should return an error."""
    print("=== Test: unknown method ===")
    proc = start_backend()
    try:
        ready = read_line(proc, timeout=15)
        assert '"ready"' in ready

        send_request(proc, 4, "nonexistent_method")
        line = read_line(proc, timeout=5)
        msg = parse_response(line)
        assert msg.get("id") == 4, f"Expected id=4, got: {msg}"
        assert msg.get("error") is not None, f"Expected error, got: {msg}"
        assert "Unknown method" in msg["error"], f"Expected 'Unknown method' error, got: {msg['error']}"
        print(f"  PASS: Unknown method returned error: {msg['error']}")
    finally:
        proc.kill()
        proc.wait()


def test_multiple_requests():
    """Test 6: Multiple requests should all get responses with correct IDs."""
    print("=== Test: multiple sequential requests ===")
    proc = start_backend()
    try:
        ready = read_line(proc, timeout=15)
        assert '"ready"' in ready

        # Send 3 requests
        send_request(proc, 10, "ping")
        send_request(proc, 11, "get_servers")
        send_request(proc, 12, "ping")

        # Read 3 responses (order may vary since each runs in a thread)
        responses = {}
        for _ in range(3):
            line = read_line(proc, timeout=10)
            msg = parse_response(line)
            responses[msg["id"]] = msg

        assert 10 in responses, "Missing response for id=10"
        assert 11 in responses, "Missing response for id=11"
        assert 12 in responses, "Missing response for id=12"
        assert responses[10]["result"] == "pong"
        assert responses[12]["result"] == "pong"
        assert isinstance(responses[11]["result"], list)

        print("  PASS: All 3 requests got correct responses")
    finally:
        proc.kill()
        proc.wait()


if __name__ == "__main__":
    print(f"Python: {PYTHON}")
    print(f"IPC Script: {IPC_SCRIPT}")
    print(f"Repo Root: {REPO_ROOT}")
    print()

    tests = [
        test_ready_event,
        test_ping,
        test_get_servers,
        test_get_versions,
        test_unknown_method,
        test_multiple_requests,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            failed += 1
        print()

    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(1 if failed > 0 else 0)
