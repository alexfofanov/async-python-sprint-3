import asyncio
import pickle
import signal
import time
from asyncio.streams import StreamReader, StreamWriter
from collections import defaultdict
from dataclasses import dataclass
from threading import Event, Thread

from config import logger

STATE_FILE = 'server_data.pickle'
PUBLIC_MESSAGES_NUM = 20
BAN_LIMIT_NUM = 3
BAN_TIME_SEC = 4 * 60 * 60
PUBLIC_ID = '__public__'
MESSAGES_PER_INTERVAL_LIMIT = 20
MESSAGES_LIMIT_INTERVAL_SEC = 60 * 60
READ_MESSAGES_TTL_SEC = 60 * 60
WAIT_DELETE_READ_MESSAGES_SEC = 60
WAIT_RESET_LIMIT_SENT_MESSAGES_SEC = 60


@dataclass
class User:
    """
    Пользователь
    """

    name: str
    exit_time: float | None = None
    ban_time: float = 0.0
    ban_num: int = 0
    session: tuple | None = None
    messages_sent_per_hour_num: int = 0
    message_limit_time: float = 0


@dataclass
class Message:
    """
    Сообщение
    """

    sender: str
    text: str
    create_at: float
    recipient: str | None = None
    read_time: float = 0


@dataclass
class Session:
    """
    Сессия
    """

    writer: StreamWriter
    user_name: str = None


class Server:
    """
    Сервер для отправки и приёма сообщений
    """

    def __init__(
        self,
        host: str = '127.0.0.1',
        port: int = 8000,
        restore_data: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.users: dict[str, User] = {}
        self.private_messages: dict[str, list[Message]] = defaultdict(list)
        self.public_messages: list[Message] = []
        self._sessions: dict[tuple, Session] = {}
        self._thread: Thread | None = None
        self._server_task: asyncio.Task | None = None
        self._delete_read_messages_task: asyncio.Task | None = None
        self._reset_limit_sent_messages_task: asyncio.Task | None = None
        self._ban_lock: asyncio.Lock = asyncio.Lock()
        self._message_lock: asyncio.Lock = asyncio.Lock()
        self._message_limit_lock: asyncio.Lock = asyncio.Lock()
        self._event: Event = Event()

        if restore_data:
            self._load_data()

    async def _server_tasks(self) -> None:
        """
        Задачи для работы сервера сообщений
        """
        server = await asyncio.start_server(
            client_connected_cb=self._client_handler,
            host=self.host,
            port=self.port,
        )

        async with server:
            self._delete_read_messages_task = asyncio.create_task(
                self._delete_read_messages()
            )
            self._reset_limit_sent_messages_task = asyncio.create_task(
                self._reset_limit_sent_messages()
            )
            logger.info(f'Start server (host:{self.host} port:{self.port})')
            self._server_task = asyncio.create_task(server.serve_forever())
            await self._stop_server()

    async def _delete_read_messages(self) -> None:
        """
        Удаление отправленных приватных сообщений после окончания
        периода READ_MESSAGES_TTL_SEC
        """
        logger.info('Start delete read messages task')
        while True:
            for messages in self.private_messages.values():
                i = 0
                while i < len(messages):
                    async with self._message_lock:
                        message = messages[i]
                        if (
                            message.read_time != 0
                            and message.read_time + READ_MESSAGES_TTL_SEC
                            < time.time()
                        ):
                            messages.remove(message)
                            logger.info(
                                (
                                    f'Delete message: From: {message.sender} '
                                    f'To: {message.recipient} '
                                    f'Text: {message.text}'
                                )
                            )
                    i += 1

            await asyncio.sleep(WAIT_DELETE_READ_MESSAGES_SEC)

    async def _reset_limit_sent_messages(self) -> None:
        """
        Сброс ограничений пользователей на отправку сообщений
        по истечению MESSAGES_LIMIT_INTERVAL_SEC
        """
        logger.info('Start reset limit sent messages task')
        while True:
            for user_name, user in self.users.items():
                async with self._message_limit_lock:
                    if (
                        user.message_limit_time > 0
                        and user.message_limit_time
                        + MESSAGES_LIMIT_INTERVAL_SEC
                        < time.time()
                    ):
                        logger.info(
                            f'Reset limit send messages for user {user_name}'
                        )
                        user.message_limit_time = 0
                        user.messages_sent_per_hour_num = 0

            await asyncio.sleep(WAIT_RESET_LIMIT_SENT_MESSAGES_SEC)

    async def _stop_server(self) -> None:
        """
        Остановка запущенных задач
        """
        while not self._event.is_set():
            await asyncio.sleep(1)
        self._delete_read_messages_task.cancel()
        self._reset_limit_sent_messages_task.cancel()
        self._server_task.cancel()

    def run(self) -> None:
        """
        Запуск сервера
        """
        signal.signal(signal.SIGINT, self._signal_handler)
        self._event = Event()
        self._thread = Thread(target=self._start_server_tasks, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """
        Остановка сервера
        """
        logger.info(f'Stop server (host:{self.host} port:{self.port})')
        self._close_clients_writers()
        self._event.set()
        self._thread.join()
        self._save_data()

    def _signal_handler(self, signal, frame):
        """
        Обработчик сигналов завершения
        """
        logger.info(
            (
                f'Stop server (host:{self.host} port:{self.port})'
                f' after signal: {signal}'
            )
        )
        self.stop()
        exit(0)

    def _start_server_tasks(self) -> None:
        """
        Запуск задач для работы сервера сообщений
        """
        asyncio.run(self._server_tasks())

    async def _client_handler(
        self, reader: StreamReader, writer: StreamWriter
    ) -> None:
        """
        Обработчик клиентской сессии
        """
        session_id = writer.get_extra_info('peername')
        logger.info(
            f'Start client (host:{session_id[0]} port:{session_id[1]})'
        )
        self._sessions[session_id] = Session(writer=writer)

        while True:
            data = await reader.read(1024)
            if not data:
                break
            line = data.decode().strip()
            logger.info(f'Server received: {line}')
            await self._command(line, session_id)

        if not writer.is_closing():
            self._close_client_writer(session_id)

    async def _write_message(self, writer: StreamWriter, text: str) -> None:
        """
        Вывод текста
        """
        output = text.encode()
        writer.write(output)
        await writer.drain()

    async def _command(self, line: str, session_id: tuple) -> None:
        """
        Обработка команд
        """
        tokens = line.split(maxsplit=1)
        command = tokens[0]
        match command:
            case 'login':
                await self._command_login(tokens[1:], session_id)
            case 'send_all':
                await self._command_send_all(tokens[1:], session_id)
            case 'send':
                await self._command_send_user(tokens[1:], session_id)
            case 'ban':
                await self._command_ban_user(tokens[1:], session_id)
            case 'quit':
                await self._command_quit(session_id)
            case _:
                text = f'Command not found: {command}'
                await self._write_message(
                    self._sessions[session_id].writer, text
                )
                logger.info(text)

    def _is_login(self, session_id: tuple) -> bool:
        """
        Проверка регистрации
        """
        return self._sessions[session_id].user_name is not None

    def _is_ban(self, user_name: str) -> bool:
        """
        Проверка бана
        """
        return self.users[user_name].ban_time > time.time()

    def _is_send_messages_limit(self, user_name) -> bool:
        """
        Проверка лимита отправленных сообщений
        """
        return (
            self.users[user_name].messages_sent_per_hour_num
            >= MESSAGES_PER_INTERVAL_LIMIT
        )

    async def _command_quit(self, session_id: tuple) -> None:
        """
        Команда выхода пользователя
        """
        self._close_client_writer(session_id)

    async def _command_login(
        self, tokens: list[str], session_id: tuple
    ) -> None:
        """
        Команда регистрация пользователя
        """
        if not tokens:
            text = 'No login name'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        user_name = tokens[0].split(maxsplit=1)[0]
        self._sessions[session_id].user_name = user_name
        user = self.users.get(user_name)
        writer = self._sessions[session_id].writer
        if user:
            user.message_limit_time = 0
            user.messages_sent_per_hour_num = 0
            await self._write_unread_messages(writer, user_name)
        else:
            self.users[user_name] = User(name=user_name)
            await self._write_some_public_messages(writer)

        self.users[user_name].session = session_id

    async def _write_unread_messages(
        self, writer: StreamWriter, user_name: str
    ) -> None:
        """
        Вывод непрочитанных публичных и приватных сообщений пользователя
        """
        for message in self.private_messages[user_name]:
            async with self._message_lock:
                if message.read_time == 0:
                    await self._write_message_to_user(writer, message)
                    message.read_time = time.time()

        for message in self.public_messages:
            if message.create_at > self.users[user_name].exit_time:
                await self._write_message_to_user(writer, message)

    async def _write_some_public_messages(self, writer) -> None:
        """
        Вывод последних (PUBLIC_MESSAGES_NUM) непрочитанных публичных сообщений
        для только что зарегистрированного пользователя
        """
        for message in self.public_messages[-PUBLIC_MESSAGES_NUM:]:
            await self._write_message_to_user(writer, message)

    async def _command_send_all(
        self, tokens: list[str], session_id: tuple
    ) -> None:
        """
        Команда отправки публичного сообщения
        """
        if not self._is_login(session_id):
            text = 'The command is not available to unregistered users'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        user_name = self._sessions[session_id].user_name
        if self._is_ban(user_name):
            during_time = round(self.users[user_name].ban_time - time.time())
            text = f'The user cannot send messages during {during_time} sec.'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        user = self.users[user_name]
        if self._is_send_messages_limit(user_name):
            during_time = round(
                user.message_limit_time
                + MESSAGES_LIMIT_INTERVAL_SEC
                - time.time()
            )
            text = f'The user cannot send messages during {during_time} sec.'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        if not tokens:
            text = 'No message text'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        message = Message(
            sender=self._sessions[session_id].user_name,
            create_at=time.time(),
            text=tokens[0],
        )

        self.public_messages.append(message)
        async with self._message_limit_lock:
            if user.message_limit_time == 0:
                user.message_limit_time = time.time()
            user.messages_sent_per_hour_num += 1

        await self._send_public_message(message)

    async def _send_public_message(self, message: Message) -> None:
        """
        Отправка публичного сообщения
        """
        for session in self._sessions.values():
            message.recipient = PUBLIC_ID
            await self._write_message_to_user(session.writer, message)

    async def _command_send_user(
        self, tokens: list[str], session_id: tuple
    ) -> None:
        """
        Команда отправки приватного сообщения
        """

        if not self._is_login(session_id):
            text = 'The command is not available to unregistered users'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        user_name = self._sessions[session_id].user_name
        if self._is_ban(user_name):
            during_time = round(self.users[user_name].ban_time - time.time())
            text = f'The user cannot send messages during {during_time} sec.'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        if not tokens:
            text = 'Recipient is not specified'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        recipient = tokens[0].split(maxsplit=1)[0]
        if recipient not in self.users:
            text = f'Recipient {recipient} does not exist'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        text = tokens[0].split(maxsplit=1)[1:]
        if not text:
            text = 'No message text'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        message = Message(
            sender=self._sessions[session_id].user_name,
            recipient=recipient,
            text=text[0],
            create_at=time.time(),
        )
        self.private_messages[recipient].append(message)

        user = self.users[recipient]
        if user.session:
            await self._write_message_to_user(
                self._sessions[user.session].writer, message
            )
            message.read_time = time.time()

    async def _write_message_to_user(
        self, writer: StreamWriter, message: Message
    ) -> None:
        """
        Отправка приватного сообщения
        """
        logger.info(
            f'Send message form {message.sender} to {message.recipient}'
        )
        text = (
            f'From: {message.sender} To: {message.recipient} '
            f'Text: {message.text}\n'
        )
        await self._write_message(writer, text)

    async def _command_ban_user(
        self, tokens: list[str], session_id: tuple
    ) -> None:
        """
        Команда отправки предупреждения пользователю
        """
        if not self._is_login(session_id):
            text = 'The command is not available to unregistered users'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        if not tokens:
            text = 'User is not specified'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        user_name = tokens[0].split(maxsplit=1)[0]
        if user_name not in self.users:
            text = f'User {user_name} does not exist'
            logger.info(text)
            await self._write_message(self._sessions[session_id].writer, text)
            return

        async with self._ban_lock:
            if self._is_ban(user_name):
                text = f'User {user_name} has already been banned'
                logger.info(text)
                await self._write_message(
                    self._sessions[session_id].writer, text
                )
                return

            self.users[user_name].ban_num += 1
            text = f'User {user_name} received new ban warning'
            logger.info(text)
            if self.users[user_name].ban_num >= BAN_LIMIT_NUM:
                self.users[user_name].ban_time = time.time() + BAN_TIME_SEC
                self.users[user_name].ban_num = 0
                text = (
                    f'User {user_name} cannot send messages during '
                    f'{BAN_TIME_SEC} sec.'
                )
                logger.info(text)

    def _close_clients_writers(self) -> None:
        """
        Закрытие всех открытых StreamWriter
        """
        for session_id in list(self._sessions):
            self._close_client_writer(session_id)

    def _close_client_writer(self, session_id: tuple) -> None:
        """
        Закрытие StreamWriter
        """
        session = self._sessions[session_id]
        session.writer.close()
        if session.user_name:
            self.users[session.user_name].exit_time = time.time()
            self.users[session.user_name].session = None
        del self._sessions[session_id]

        logger.info(f'Stop client (host:{session_id[0]} port:{session_id[1]})')

    def _save_data(self) -> None:
        """
        Сохранение данных сервера
        """
        with open(STATE_FILE, 'wb') as file:
            pickle.dump(
                (self.users, self.private_messages, self.public_messages),
                file,
            )

        logger.info('Server save state')

    def _load_data(self) -> None:
        """
        Восстановление данных сервера
        """
        with open(STATE_FILE, 'rb') as file:
            self.users, self.private_messages, self.public_messages = (
                pickle.load(file)
            )
        logger.info('Server load state')
