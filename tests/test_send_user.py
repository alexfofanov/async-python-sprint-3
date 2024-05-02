import unittest
from asyncio.streams import StreamWriter
from unittest.mock import MagicMock

from server import Server, User

MESSAGE_TEXT = 'message text'
NO_MESSAGE_WARNING = 'No message text'
NO_USER = 'no_user'
RECIPIENT_NOT_EXIST_WARNING = f'Recipient {NO_USER} does not exist'
NO_RECIPIENT_WARNING = 'Recipient is not specified'


class TestServerCommandSendUser(unittest.IsolatedAsyncioTestCase):
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

    async def test_command_send_private_no_recipient(self):
        await self.server._command_send_user([], self.session_id1)
        self.writer_mock.write.assert_called_once_with(
            NO_RECIPIENT_WARNING.encode()
        )

    async def test_command_send_private_recipient_not_exist(self):
        await self.server._command_send_user([NO_USER], self.session_id1)
        self.writer_mock.write.assert_called_once_with(
            RECIPIENT_NOT_EXIST_WARNING.encode()
        )

    async def test_command_send_user_no_text(self):
        await self.server._command_send_user(
            [self.user2.name], self.session_id1
        )
        self.writer_mock.write.assert_called_once_with(
            NO_MESSAGE_WARNING.encode()
        )

    async def test_command_send_all(self):
        await self.server._command_send_user(
            [f'{self.user2.name} {MESSAGE_TEXT}'], self.session_id1
        )
        print(self.server.private_messages)
        self.assertEqual(len(self.server.private_messages[self.user2.name]), 1)
        self.assertEqual(
            self.server.private_messages[self.user2.name][0].text, MESSAGE_TEXT
        )
