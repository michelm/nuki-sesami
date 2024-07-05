from __future__ import annotations
import argparse
import asyncio
import importlib.metadata
import json
import logging
import os
import socket
import sys
from logging import Logger
from typing import Dict

import aiomqtt

from nuki_sesami.config import SesamiConfig, get_config
from nuki_sesami.lock import NukiDoorsensorState, NukiLockState
from nuki_sesami.state import DoorMode, DoorRequestState, DoorState
from nuki_sesami.util import get_config_path, get_prefix, getlogger


async def mqtt_publish_sesami_request_state(client, sesamibluez, state: DoorRequestState):
    device = sesamibluez.nuki_device
    sesamibluez.logger.info('[mqtt] publish sesami/%s/request/state=%i', device, state.value)
    await client.publish(f"sesami/{device}/request/state", state.value)


async def bluetooth_publish_sesami_status(sesamibluez, interval: int = 3):
    while True:
        await asyncio.sleep(interval)
        sesamibluez.publish_status()


class SesamiBluetoothAgent(asyncio.Protocol):
    '''Acts as broker between smartphones via bluetooth and the nuki-sesami
    eletrical door opener via mqtt.

    Subscribes as client to MQTT eletrical door opener topics from 'Nuki Sesami'.
    Received door commands from smartphones are forwarded to the MQTT broker.
    '''
    def __init__(self, logger: Logger, config: SesamiConfig, version: str):
        self._version = version
        self._logger = logger
        self._nuki_device = config.nuki_device
        self._nuki_lock = NukiLockState.undefined
        self._nuki_doorsensor = NukiDoorsensorState.unknown
        self._door_state = DoorState.closed
        self._door_mode = DoorMode.openclose
        self._relay_openclose = False
        self._relay_openhold = False
        self._relay_opendoor = False
        self._clients = [] # list of connected bluetooth clients
        self._background_tasks = set()

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        self.logger.info('[bluez] client connected %s', peername)
        self._clients.append(transport)
        self.publish_status(transport)

    def connection_lost(self, exc):
        '''Remove the client(transport) from the list of clients'''
        self.logger.info('[bluez] client disconnected %r', exc)
        self._clients = [c for c in self._clients if not c.is_closing()]

    def run_coroutine(self, coroutine):
        '''Wraps the coroutine into a task and schedules its execution

        The task will be added to the set of background tasks.
        This creates a strong reference.

        To prevent keeping references to finished tasks forever,
        the task removes its own reference from the set of background tasks
        after completion.
        '''
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def process_request(self, request: str):
        if not request:
            return

        try:
            req = json.loads(request)
            if req["method"] == "set" and "door_request_state" in req["params"]:
                state = DoorRequestState(req["params"]["door_request_state"])
                self.run_coroutine(mqtt_publish_sesami_request_state(self._mqtt, self, state))
        except json.decoder.JSONDecodeError:
            self.logger.exception('[bluez] failed to process request(%s)', request)

    def data_received(self, data):
        msg = data.decode()
        self.logger.debug('[bluez] data received: %r', msg)
        for m in [s for s in msg.split('\n') if s]:
            self.process_request(m)

    def get_status(self) -> Dict:
        return {
            "nuki": {
                "lock": self._nuki_lock.value,
                "doorsensor": self._nuki_doorsensor.value
            },
            "door": {
                "state": self._door_state.value,
                "mode": self._door_mode.value
            },
            "relay": {
                "openclose": self._relay_openclose,
                "openhold": self._relay_openhold,
                "opendoor": self._relay_opendoor
            },
            "version": self._version
        }
    
    def get_jsonrpc_status_notification(self) -> str:
        status = self.get_status()
        return json.dumps({
            "jsonrpc": "2.0",
            "method": "status",
            "params": status
        })

    def publish_status(self, transport: asyncio.BaseTransport | None = None):
        '''Publish status to a specific or all smartphones'''
        msg = self.get_jsonrpc_status_notification()

        if transport:
            self.logger.debug("[bluez] publish_status(N)=%s", msg)
            transport.write(str(msg + '\n').encode())
        elif self._clients:
            self.logger.debug("[bluez] publish_status(U%i)=%s", len(self._clients), msg)
            for client in self._clients:
                client.write(str(msg + '\n').encode())

    def activate(self, client: aiomqtt.Client):
        self._mqtt = client
        self.run_coroutine(bluetooth_publish_sesami_status(self))

    @property
    def logger(self) -> Logger:
        return self._logger

    @property
    def nuki_device(self) -> str:
        return self._nuki_device

    @property
    def nuki_lock(self) -> NukiLockState:
        return self._nuki_lock

    @nuki_lock.setter
    def nuki_lock(self, state: NukiLockState):
        self._nuki_lock = state
        self.publish_status()

    @property
    def nuki_doorsensor(self) -> NukiDoorsensorState:
        return self._nuki_doorsensor

    @nuki_doorsensor.setter
    def nuki_doorsensor(self, state: NukiDoorsensorState):
        self._nuki_doorsensor = state
        self.publish_status()

    @property
    def door_state(self) -> DoorState:
        return self._door_state

    @door_state.setter
    def door_state(self, state: DoorState):
        self._door_state = state
        self.publish_status()

    @property
    def door_mode(self) -> DoorMode:
        return self._door_mode

    @door_mode.setter
    def door_mode(self, mode: DoorMode):
        self._door_mode = mode
        self.publish_status()

    @property
    def relay_openclose(self) -> bool:
        return self._relay_openclose

    @relay_openclose.setter
    def relay_openclose(self, state: bool):
        self._relay_openclose = state
        self.publish_status()

    @property
    def relay_openhold(self) -> bool:
        return self._relay_openhold

    @relay_openhold.setter
    def relay_openhold(self, state: bool):
        self._relay_openhold = state
        self.publish_status()

    @property
    def relay_opendoor(self) -> bool:
        return self._relay_opendoor

    @relay_opendoor.setter
    def relay_opendoor(self, state: bool):
        self._relay_opendoor = state
        self.publish_status()


async def mqtt_receiver(client: aiomqtt.Client, agent: SesamiBluetoothAgent):
    async for msg in client.messages:
        payload = msg.payload.decode()
        topic = str(msg.topic)
        agent.logger.info('[mqtt] receive %s=%s', topic, payload)
        if topic == f"nuki/{agent.nuki_device}/state":
            agent.nuki_lock = NukiLockState(int(payload))
        elif topic == f"nuki/{agent.nuki_device}/doorsensorState":
            agent.nuki_doorsensor = NukiDoorsensorState(int(payload))
        elif topic == f"sesami/{agent.nuki_device}/state":
            agent.door_state = DoorState(int(payload))
        elif topic == f"sesami/{agent.nuki_device}/mode":
            agent.door_mode = DoorMode(int(payload))
        elif topic == f"sesami/{agent.nuki_device}/relay/openclose":
            agent.relay_openclose = bool(int(payload))
        elif topic == f"sesami/{agent.nuki_device}/relay/openhold":
            agent.relay_openhold = bool(int(payload))
        elif topic == f"sesami/{agent.nuki_device}/relay/opendoor":
            agent.relay_opendoor = bool(int(payload))


async def activate(logger: Logger, config: SesamiConfig, version: str):
    blueagent = SesamiBluetoothAgent(logger, config, version)
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.bind((config.bluetooth_macaddr, config.bluetooth_channel))
    blueserver = await loop.create_server(lambda: blueagent, sock=sock, backlog=config.bluetooth_backlog)

    async with aiomqtt.Client(config.mqtt_host, port=config.mqtt_port,
            username=config.mqtt_username, password=config.mqtt_password) as client:
        blueagent.activate(client)
        device = blueagent.nuki_device
        await client.subscribe(f"nuki/{device}/state")
        await client.subscribe(f"nuki/{device}/doorsensorState")
        await client.subscribe(f"sesami/{device}/state")
        await client.subscribe(f"sesami/{device}/mode")
        await client.subscribe(f"sesami/{device}/relay/openclose")
        await client.subscribe(f"sesami/{device}/relay/openhold")
        await client.subscribe(f"sesami/{device}/relay/opendoor")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(mqtt_receiver(client, blueagent))
            tg.create_task(blueserver.serve_forever())


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami-bluez',
        description='Receive door commands from smartphones via bluetooth and forwards these to sesami-nuki',
        epilog='Belrog: you shall not pass!',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('-p', '--prefix',
                        help="runtime system root; e.g. '~/.local' or '/'",
                        type=str, default=None)
    parser.add_argument('-c', '--cpath',
                        help="configuration path; e.g. '/etc/nuki-sesami' or '~/.config/nuki-sesami'",
                        type=str, default=None)
    parser.add_argument('-V', '--verbose',
                        help="be verbose", action='store_true')
    parser.add_argument('-v', '--version',
                        help="print version and exit", action='store_true')

    args = parser.parse_args()
    version = importlib.metadata.version('nuki-sesami')
    if args.version:
        print(version)
        sys.exit(0)

    prefix = args.prefix or get_prefix()
    cpath = args.cpath or get_config_path()
    logpath = os.path.join(prefix, 'var/log/nuki-sesami-bluez')

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami-bluez', logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    config = get_config(cpath)

    logger.info("version          : %s", version)
    logger.info("prefix           : %s", prefix)
    logger.info("config-path      : %s", cpath)
    logger.info("nuki.device      : %s", config.nuki_device)
    logger.info("mqtt.host        : %s", config.mqtt_host)
    logger.info("mqtt.port        : %i", config.mqtt_port)
    logger.info("mqtt.username    : %s", config.mqtt_username)
    logger.info("mqtt.password    : %s", '***')
    logger.info("bluetooth.macaddr: %s", config.bluetooth_macaddr)
    logger.info("bluetooth.channel: %i", config.bluetooth_channel)
    logger.info("bluetooth.backlog: %i", config.bluetooth_backlog)

    try:
        asyncio.run(activate(logger, config, version))
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
