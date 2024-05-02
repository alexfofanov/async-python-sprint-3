import time

from server import Server


def main() -> None:
    server = Server()
    server.run()
    print('Start server...')
    time.sleep(500)
    print('Stop server...')
    server.stop()

    server = Server(restore_data=True)
    server.run()
    time.sleep(200)
    server.stop()


if __name__ == '__main__':
    main()
