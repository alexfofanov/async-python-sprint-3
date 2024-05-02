import asyncio
import signal

from aioconsole import ainput

from config import logger

EXIT_COMMAND = 'quit'


class Client:
    def __init__(self, host: str = '127.0.0.1', port: int = 8000) -> None:
        self.host = host
        self.port = port
        self._reader = None
        self._writer = None
        self._receive_task: asyncio.Task | None = None
        self._send_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        """
        Запуск
        """
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        self._reader, self._writer = await asyncio.open_connection(
            self.host, self.port
        )
        self._receive_task = asyncio.create_task(self._receive())
        self._send_task = asyncio.create_task(self._send())
        await self._stop_client_task()

    async def _send(self) -> None:
        """
        Отправка
        """
        while True:
            msg: str = await ainput('>')
            self._writer.write(msg.encode())
            await self._writer.drain()
            if msg == EXIT_COMMAND:
                self._stop_event.set()
            await asyncio.sleep(0.1)

    async def _receive(self) -> None:
        """
        Получение
        """
        while True:
            response: bytes = await self._reader.read(1000)
            if not response:
                logger.info('Closed by the server')
                self._stop_event.set()
                break
            logger.info(f'{response.decode()}')

    async def _stop_client_task(self) -> None:
        """
        Задача остановки клиента
        """
        while True:
            if self._stop_event.is_set():
                self._stop()
                break
            await asyncio.sleep(0)

    def _stop(self) -> None:
        """
        Остановка
        """
        if self._writer:
            self._writer.close()
        self._receive_task.cancel()
        self._send_task.cancel()

    def signal_handler(self, signal, frame):
        """
        Обработчик сигналов завершения
        """
        self._stop()
        exit(0)


if __name__ == '__main__':
    client = Client()
    asyncio.run(client.run())
