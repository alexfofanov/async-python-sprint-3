from unittest import TestCase

from server import Server

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8000

INIT_HOST = '192.168.1.1'
INIT_PORT = 8080


class ServerTest(TestCase):
    def test_server_default_init(self):
        self.server = Server()
        self.assertEqual(self.server.host, DEFAULT_HOST)
        self.assertEqual(self.server.port, DEFAULT_PORT)

    def test_server_init(self):
        self.server = Server(host=INIT_HOST, port=INIT_PORT)
        self.assertEqual(self.server.host, INIT_HOST)
        self.assertEqual(self.server.port, INIT_PORT)
