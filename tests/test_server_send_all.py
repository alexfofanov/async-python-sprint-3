import unittest
from asyncio.streams import StreamWriter
from unittest.mock import MagicMock

from server import Server, User

MESSAGE_TEXT = 'message text'
NO_MESSAGE_TEXT = 'No message text'


class TestServerCommandSendAll(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = Server()
        self.session_id1 = ('127.0.0.1', 12345)
        self.session_id2 = ('127.0.0.1', 12346)
        self.writer_mock = MagicMock(spec=StreamWriter)
        self.server._sessions[self.session_id1] = MagicMock(
            writer=self.writer_mock, user_name=None
        )
        self.user1 = User(name='user1')
        self.user2 = User(name='user2')
        self.server.users = {
            self.user1.name: self.user1,
            self.user2.name: self.user2,
        }
        self.server._sessions[self.session_id1] = MagicMock(
            writer=self.writer_mock, user_name=self.user1.name
        )
        self.server._sessions[self.session_id2] = MagicMock(
            writer=self.writer_mock, user_name=self.user2.name
        )

    async def test_command_send_all_no_text(self):
        await self.server._command_send_all([], self.session_id1)
        self.writer_mock.write.assert_called_once_with(
            NO_MESSAGE_TEXT.encode()
        )

    async def test_command_send_all(self):
        await self.server._command_send_all([MESSAGE_TEXT], self.session_id1)
        self.assertEqual(len(self.server.public_messages), 1)
        self.assertEqual(self.server.public_messages[0].text, MESSAGE_TEXT)
