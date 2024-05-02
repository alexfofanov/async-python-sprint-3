import unittest
from asyncio.streams import StreamWriter
from unittest.mock import MagicMock

from server import Server

NO_LOGIN_TEXT = 'No login name'


class TestServerCommandLogin(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = Server()
        self.session_id = ('127.0.0.1', 12345)
        self.writer_mock = MagicMock(spec=StreamWriter)
        self.server._sessions[self.session_id] = MagicMock(
            writer=self.writer_mock, user_name=None
        )

    async def test_command_login_no_tokens(self):
        await self.server._command_login([], self.session_id)
        self.writer_mock.write.assert_called_once_with(NO_LOGIN_TEXT.encode())

    async def test_command_login_user_already_exists(self):
        self.server.users = {'user1': MagicMock()}
        await self.server._command_login(['user1'], self.session_id)
        self.assertTrue(self.server.users['user1'].session)
        self.assertEqual(self.server.users['user1'].session, self.session_id)
        self.assertEqual(
            self.server._sessions[self.session_id].user_name, 'user1'
        )

    async def test_command_login_user_not_already_exists(self):
        self.server.users = {}
        await self.server._command_login(['user1'], self.session_id)
        self.assertTrue(self.server.users['user1'])
        self.assertEqual(self.server.users['user1'].session, self.session_id)
        self.assertEqual(
            self.server._sessions[self.session_id].user_name, 'user1'
        )

    async def test_is_login(self):
        await self.server._command_login(['user1'], self.session_id)
        self.assertTrue(self.server._is_login(self.session_id))
