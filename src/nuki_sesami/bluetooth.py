import argparse
import json
import logging
import os
import asyncio
import importlib.metadata
from logging import Logger

import aiomqtt

from nuki_sesami.config import SesamiConfig, get_config
from nuki_sesami.lock import NukiDoorsensorState, NukiLockState
from nuki_sesami.state import DoorMode, DoorState, DoorRequestState
from nuki_sesami.util import get_config_path, get_prefix, getlogger


async def mqtt_subscribe_nuki_state(client, sesamibluez):
    device = sesamibluez.nuki_device
    await client.subscribe(f"nuki/{device}/state")
    async for msg in client.messages:
        sesamibluez.logger.info("[mqtt] nuki/%s/state=%s", device, msg.payload)
        sesamibluez.nuki_lock = NukiLockState(int(msg.payload))


async def mqtt_subscribe_nuki_doorsensor_state(client, sesamibluez):
    device = sesamibluez.nuki_device
    await client.subscribe(f"nuki/{device}/doorsensorState")
    async for msg in client.messages:
        sesamibluez.logger.info("[mqtt] nuki/%s/doorsensorState=%s", device, msg.payload)
        sesamibluez.nuki_doorsensor = NukiDoorsensorState(int(msg.payload))


async def mqtt_subscribe_sesami_state(client, sesamibluez):
    device = sesamibluez.nuki_device
    await client.subscribe(f"sesami/{device}/state")
    async for msg in client.messages:
        sesamibluez.logger.info("[mqtt] sesami/%s/state=%s", device, msg.payload)
        sesamibluez.door_state = DoorState(int(msg.payload))


async def mqtt_subscribe_sesami_mode(client, sesamibluez):
    device = sesamibluez.nuki_device
    await client.subscribe(f"sesami/{device}/mode")
    async for msg in client.messages:
        sesamibluez.logger.info("[mqtt] sesami/%s/mode=%s", device, msg.payload)
        sesamibluez.door_mode = DoorMode(int(msg.payload))


async def mqtt_subscribe_sesami_relay_openhold(client, sesamibluez):
    device = sesamibluez.nuki_device
    await client.subscribe(f"sesami/{device}/relay/openhold")
    async for msg in client.messages:
        sesamibluez.logger.info("[mqtt] sesami/%s/relay/openhold=%s", device, msg.payload)
        sesamibluez.relay_openhold = msg.payload == "1"


async def mqtt_subscribe_sesami_relay_openclose(client, sesamibluez):
    device = sesamibluez.nuki_device
    await client.subscribe(f"sesami/{device}/relay/openclose")
    async for msg in client.messages:
        sesamibluez.logger.info("[mqtt] sesami/%s/relay/openclose=%s", device, msg.payload)
        sesamibluez.relay_openclose = msg.payload == "1"


async def mqtt_subscribe_sesami_relay_opendoor(client, sesamibluez):
    device = sesamibluez.nuki_device
    await client.subscribe(f"sesami/{device}/relay/opendoor")
    async for msg in client.messages:
        sesamibluez.logger.info("[mqtt] sesami/%s/relay/opendoor=%s", device, msg.payload)
        sesamibluez.relay_opendoor = msg.payload == "1"


async def mqtt_publish_sesami_request_state(client, sesamibluez, state: DoorRequestState):
    device = sesamibluez.nuki_device
    sesamibluez.logger.info('[mqtt] publish sesami/%s/request/state=%i', device, state.value)
    await client.publish(f"sesami/{device}/request/state", state.value)


class SesamiBluetoothAgent(asyncio.Protocol):
    '''Acts as broker between smartphones via bluetooth and the nuki-sesami
    eletrical door opener via mqtt.

    Subscribes as client to MQTT eletrical door opener topics from 'Nuki Sesami'.
    Received door commands from smartphones are forwarded to the MQTT broker.
    '''
    def __init__(self, logger: Logger, config: SesamiConfig):
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
        self.logger.info('[bluez] client connected {}'.format(peername))
        self._clients.append(transport)
        self.publish_status(transport)

    def connection_lost(self, exc):
        '''Remove the client(transport) from the list of clients'''
        self.logger.info('[bluez] client disconnected {}'.format(exc))
        self._clients = [c for c in self._clients if not c.is_closing()]

    def _asyncio_schedule(self, coroutine):
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

    def _process_request(self, request):
        if not request:
            return

        try:
            req = json.loads(request)
            if req["method"] == "set" and "door_request_state" in req["params"]:
                state = DoorRequestState(req["params"]["door_request_state"])
                self.logger.info('[bluez] publish door request state: {!r}'.format(state))
                self._asyncio_schedule(mqtt_publish_sesami_request_state(self._mqtt, self, state))                
        except Exception as e:
            self.logger.error('[bluez] failed to process request: %s', e)

    def data_received(self, data):
        msg = data.decode()
        self.logger.debug('[bluez] data received: {!r}'.format(msg))
        try:
            for m in [s for s in msg.split('\n') if s]:
                self._process_request(m)
        except Exception as e:
            self.logger.error('[bluez] failed to parse message: %s', e)

    def publish_status(self, transport: asyncio.BaseTransport | None = None):
        '''Publish status to a specific or all smartphones'''
        status = json.dumps({
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
            }
        })
        self.logger.debug("[bluez] publish_status=%s", status)

        if transport is None:            
            for client in self._clients:
                client.write(status.encode())
        else:
            transport.write(status.encode())

    def mqtt_client(self, client: aiomqtt.Client):
        self._mqtt = client

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


async def activate(logger: Logger, config):
    blueagent = SesamiBluetoothAgent(logger, config)
    loop = asyncio.get_running_loop()
    blueserver = await loop.create_server(lambda: blueagent, '127.0.0.1', 8888)

    async with aiomqtt.Client(config.mqtt_host, port=config.mqtt_port, 
            username=config.mqtt_username, password=config.mqtt_password) as client:
        blueagent.mqtt_client(client)
        await mqtt_subscribe_nuki_state(client, blueagent)
        await mqtt_subscribe_nuki_doorsensor_state(client, blueagent)
        await mqtt_subscribe_sesami_state(client, blueagent)
        await mqtt_subscribe_sesami_mode(client, blueagent)
        await blueserver.serve_forever()


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

    args = parser.parse_args()
    prefix = args.prefix or get_prefix()
    cpath = args.cpath or get_config_path()
    logpath = os.path.join(prefix, 'var/log/nuki-sesami-bluez')

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami-bluez', logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    config = get_config(cpath)

    logger.info("version          : %s", importlib.metadata.version('nuki-sesami'))
    logger.info("prefix           : %s", prefix)
    logger.info("config-path      : %s", cpath)
    logger.info("nuki.device      : %s", config.nuki_device)
    logger.info("mqtt.host        : %s", config.mqtt_host)
    logger.info("mqtt.port        : %i", config.mqtt_port)
    logger.info("mqtt.username    : %s", config.mqtt_username)
    logger.info("mqtt.password    : %s", '***')
    logger.info("bluetooth.macaddr: %s", config.bluetooth_macaddr)
    logger.info("bluetooth.port   : %i", config.bluetooth_port)

    try:
        asyncio.run(activate(logger, config))
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
