import socket
import subprocess
import sys
import time
import urllib.request


HOST = "127.0.0.1"


def get_free_tcp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


class MotoServer:
    """A moto server subprocess, started on entering a ``with`` block and stopped on leaving it

    Running moto in a subprocess keeps its request handlers out of the test
    process. There, the ``error`` warning filter that conftest.py sets would
    raise any warning that moto emits while handling a request, and the
    request would fail.
    """

    def __init__(self, port=None, timeout=30):
        self.port = port or get_free_tcp_port()
        self.timeout = timeout
        self.process = None

    @property
    def endpoint_url(self):
        return "http://%s:%d" % (HOST, self.port)

    def start(self):
        # The subprocess inherits stdout and stderr, so pytest captures its
        # request log with the output of the running test and shows it if
        # that test fails.
        self.process = subprocess.Popen(
            [sys.executable, "-m", "moto.server", "-H", HOST, "-p", str(self.port)])
        try:
            self.wait_until_ready()
        except Exception:
            self.stop()
            raise

    def wait_until_ready(self):
        deadline = time.monotonic() + self.timeout
        while True:
            if self.process.poll() is not None:
                raise RuntimeError(
                    "moto server exited with code %d" % self.process.returncode)
            try:
                with urllib.request.urlopen(
                        self.endpoint_url + "/moto-api/config", timeout=1):
                    return
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "moto server did not respond within %d seconds" % self.timeout)
                time.sleep(0.2)

    def stop(self):
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
