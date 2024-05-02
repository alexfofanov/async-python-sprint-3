import unittest
from asyncio.streams import StreamWriter
from unittest.mock import MagicMock

from server import BAN_LIMIT_NUM, Server, User

NO_USER = 'no_user'
USER_NOT_EXIST_WARNING = f'Recipient {NO_USER} does not exist'
NO_USER_WARNING = 'User is not specified'


class TestServerCommandBanUser(unittest.IsolatedAsyncioTestCase):
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

    async def test_command_ban_user_no_user(self):
        await self.server._command_ban_user([], self.session_id1)
        self.writer_mock.write.assert_called_once_with(
            NO_USER_WARNING.encode()
        )

    async def test_command_ban_user_not_exist(self):
        await self.server._command_send_user([NO_USER], self.session_id1)
        self.writer_mock.write.assert_called_once_with(
            USER_NOT_EXIST_WARNING.encode()
        )

    async def test_command_ban_user(self):
        self.assertEqual(self.user2.ban_num, 0)
        await self.server._command_ban_user(
            [f'{self.user2.name}'], self.session_id1
        )
        self.assertEqual(self.user2.ban_num, 1)

    async def test_is_ban(self):
        self.assertEqual(self.user2.ban_num, 0)
        for i in range(BAN_LIMIT_NUM):
            await self.server._command_ban_user(
                [f'{self.user2.name}'], self.session_id1
            )
        self.assertTrue(self.server._is_ban(self.user2.name))
