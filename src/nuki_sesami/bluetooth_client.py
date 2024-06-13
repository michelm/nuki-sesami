import sys
import socket
import json
import asyncio
import argparse
import logging
import importlib.metadata

from nuki_sesami.state import DoorRequestState


async def send_alive(writer: asyncio.StreamWriter, addr: str, channel:int, logger: logging.Logger):
    logger.info('send[%s, ch=%i] alive', addr, channel)
    msg = json.dumps({"jsonrpc": "2.0", "method": "alive"})
    writer.write(str(msg + '\n').encode())
    await writer.drain()


async def send_door_request(writer: asyncio.StreamWriter, state: DoorRequestState,addr: str, channel:int, logger: logging.Logger):
    logger.info('send[%s, ch=%i] door_request(%s:%i)', addr, channel, state.name, state.value)
    msg = json.dumps({"jsonrpc": "2.0", "method": "set", "params": {"door_request_state":state.value}})
    writer.write(str(msg + '\n').encode())
    await writer.drain()


async def send_alives(writer: asyncio.StreamWriter, logger: logging.Logger, addr: str, channel: int):
    while True:
        await send_alive(writer, addr, channel, logger)
        await asyncio.sleep(5)


async def send_requests(writer: asyncio.StreamWriter, logger: logging.Logger, addr: str, channel: int):
    while True:
        await send_door_request(writer, DoorRequestState.open, addr, channel, logger)
        await asyncio.sleep(20)
        await send_door_request(writer, DoorRequestState.openhold, addr, channel, logger)
        await asyncio.sleep(30)
        await send_door_request(writer, DoorRequestState.close, addr, channel, logger)


async def receive_status(reader: asyncio.StreamReader, logger: logging.Logger, addr: str, channel: int):
    while True:
        data = await reader.read(1024)
        if not data:
            break
        logger.info('recv[%s, ch=%i] status(%s)', addr, channel, data.decode())


async def sesami_bluetooth_client(logger: logging.Logger, addr: str, channel: int, test_door_requests: bool):
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.connect((addr, channel))
    reader, writer = await asyncio.open_connection(sock=sock)
    tasks = set()

    task = asyncio.create_task(send_alives(
        writer, logger, addr, channel
    ))
    tasks.add(task)
    task.add_done_callback(tasks.discard)

    if test_door_requests:
        task = asyncio.create_task(send_requests(
            writer, logger, addr, channel
        ))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    await receive_status(reader, logger, addr, channel)


def getlogger(name, level):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    return logger


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami-bluetest',
        description='bluetooth test client that mimics the behavior of a nuki-sesami smartphone app',
        epilog='You never know if the cat is in or not',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('-a', '--addr',
                        help="blueooth mac address of the nuki-sesami device (raspberry-pi)",
                        type=str, default=None)
    parser.add_argument('-c', '--channel',
                        help="blueooth channel of the nuki-sesami device (raspberry-pi)",
                        type=int, default=None)

    parser.add_argument('-t', '--test-door-requests',
                        help="test door requests (open, openhold, close)",
                        action='store_true')

    args = parser.parse_args()
    logger = getlogger('nuki-sesami-bluetest', logging.DEBUG)

    logger.info("version          : %s", importlib.metadata.version('nuki-sesami'))
    logger.info("bluetooth.macaddr: %s", args.addr)
    logger.info("bluetooth.channel: %i", args.channel)

    try:
        asyncio.run(sesami_bluetooth_client(logger, args.addr, args.channel, args.test_door_requests))
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
