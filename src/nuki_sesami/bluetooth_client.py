import argparse
import asyncio
import importlib.metadata
import json
import logging
import socket
import sys

from nuki_sesami.state import DoorRequestState


async def send_alive(writer: asyncio.StreamWriter, addr: str, channel:int, logger: logging.Logger):
    logger.info('send[%s, ch=%i] alive', addr, channel)
    msg = json.dumps({"jsonrpc": "2.0", "method": "alive"})
    writer.write(str(msg + '\n').encode())
    await writer.drain()


async def send_door_request(writer: asyncio.StreamWriter, state: DoorRequestState, addr: str,
                            channel:int, logger: logging.Logger):
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


async def receive_status(reader: asyncio.StreamReader, logger: logging.Logger, addr: str, channel: int, maxrecv: int):
    n = maxrecv
    c = 0
    while (n < 0) or (c < n):
        data = await reader.read(1024)
        if not data:
            break
        logger.info('recv[%s, ch=%i] status(%s)', addr, channel, data.decode())
        c += 1


async def sesami_bluetooth_client(logger: logging.Logger, addr: str, channel: int, request: int,
                                  test_requests: bool, maxrecv: int):
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.connect((addr, channel))
    reader, writer = await asyncio.open_connection(sock=sock)
    tasks = set()

    task = asyncio.create_task(send_alives(
        writer, logger, addr, channel
    ))
    tasks.add(task)
    task.add_done_callback(tasks.discard)

    if request:
        task = asyncio.create_task(send_door_request(
            writer, DoorRequestState(request), addr, channel, logger
        ))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    elif test_requests:
        task = asyncio.create_task(send_requests(
            writer, logger, addr, channel
        ))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    await receive_status(reader, logger, addr, channel, maxrecv)


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
    parser.add_argument('-r', '--door-request',
                        help="send door request (1=close, 2=open, 3=openhold)",
                        type=int, default=0, choices=[1, 2, 3])
    parser.add_argument('-t', '--test-requests',
                        help="test door requests (open, openhold, close)",
                        action='store_true')
    parser.add_argument('-m', '--maxrecv',
                        help="maximum number status messages to receive (-1 == infinite)",
                        type=int, default=0)
    parser.add_argument('-V', '--verbose',
                        help="be verbose", action='store_true')
    parser.add_argument('-v', '--version',
                        help="print version and exit", action='store_true')

    args = parser.parse_args()

    version = importlib.metadata.version('nuki-sesami')
    if args.version:
        print(version)
        sys.exit(0)

    level = logging.DEBUG if args.verbose else logging.INFO
    logger = getlogger('nuki-sesami-bluetest', level)
    logger.debug("version          : %s", version)
    logger.debug("bluetooth.macaddr: %s", args.addr)
    logger.debug("bluetooth.channel: %i", args.channel)
    logger.debug("door_request     : %i", args.door_request)
    logger.debug("test_requests    : %s", args.test_requests)
    logger.debug("maxrecv          : %i", args.maxrecv)

    try:
        asyncio.run(sesami_bluetooth_client(logger,
            args.addr, args.channel, args.door_request, args.test_requests, args.maxrecv))
    except KeyboardInterrupt:
        logger.debug("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
