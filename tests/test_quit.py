import unittest
from asyncio.streams import StreamWriter
from unittest.mock import MagicMock

from server import Server, User

NO_USER = 'no_user'
USER_NOT_EXIST_WARNING = f'Recipient {NO_USER} does not exist'
NO_USER_WARNING = 'User is not specified'


class TestServerCommandQuit(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = Server()
        self.session_id = ('127.0.0.1', 12345)
        self.writer_mock = MagicMock(spec=StreamWriter)
        self.user1 = User(name='user1')
        self.server.users = {self.user1.name: self.user1}
        self.server._sessions[self.session_id] = MagicMock(
            writer=self.writer_mock, user_name=self.user1.name
        )

    async def test_command_quit(self):
        self.assertIsNotNone(self.server._sessions[self.session_id].user_name)
        await self.server._command_quit(self.session_id)
        self.assertNotIn(self.session_id, self.server._sessions)
