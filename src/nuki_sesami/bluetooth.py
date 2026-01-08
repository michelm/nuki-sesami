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

import aiomqtt

from nuki_sesami.config import SesamiConfig, get_config
from nuki_sesami.lock import NukiDoorsensorState, NukiLockState
from nuki_sesami.state import DoorMode, DoorRequestState, DoorState
from nuki_sesami.util import get_config_path, get_prefix, getlogger


async def mqtt_publish_sesami_request_state(client, agent, state: DoorRequestState) -> None:
    device = agent.nuki_device
    agent.logger.info("[mqtt] publish sesami/%s/request/state=%i", device, state.value)
    await client.publish(f"sesami/{device}/request/state", state.value)


async def bluetooth_publish_sesami_status(agent, interval: int = 3) -> None:
    while True:
        await asyncio.sleep(interval)
        agent.publish_status()


class SesamiBluetoothProtocol(asyncio.Protocol):
    """Handles an individual bluetooth connection with buffering."""

    def __init__(self, agent: SesamiBluetoothAgent):
        self._agent = agent
        self._transport: asyncio.Transport | None = None
        self._buffer = ""

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore
        peername = transport.get_extra_info("peername")
        self._agent.logger.info("[bluez] client connected %s", peername)
        self._agent.add_protocol(self)
        self.send_status()

    def connection_lost(self, exc: Exception | None) -> None:
        self._agent.logger.info("[bluez] client disconnected %r", exc)
        self._agent.remove_protocol(self)

    def data_received(self, data: bytes) -> None:
        try:
            self._buffer += data.decode()
        except UnicodeDecodeError:
            self._agent.logger.error("[bluez] failed to decode data: %r", data)
            return

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                self._agent.logger.debug("[bluez] data received: %r", line)
                self.process_request(line)

    def process_request(self, request: str) -> None:
        try:
            req = json.loads(request)
            if req.get("method") == "set" and "door_request_state" in req.get("params", {}):
                state = DoorRequestState(req["params"]["door_request_state"])
                self._agent.run_coroutine(mqtt_publish_sesami_request_state(self._agent.mqtt, self._agent, state))
        except (json.JSONDecodeError, ValueError, TypeError):
            self._agent.logger.exception("[bluez] failed to process request(%s)", request)

    def send_status(self) -> None:
        if not self._transport or self._transport.is_closing():
            return
        msg = self._agent.get_jsonrpc_status_notification()
        self._agent.logger.debug("[bluez] send_status=%s", msg)
        self._transport.write(str(msg + "\n").encode())


class SesamiBluetoothAgent:
    """Acts as broker between smartphones via bluetooth and the nuki-sesami
    eletrical door opener via mqtt.

    Manages shared state across all connected bluetooth clients.
    """

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
        self._protocols: list[SesamiBluetoothProtocol] = []
        self._background_tasks: set[asyncio.Task] = set()
        self._mqtt: aiomqtt.Client | None = None

    def add_protocol(self, protocol: SesamiBluetoothProtocol) -> None:
        self._protocols.append(protocol)

    def remove_protocol(self, protocol: SesamiBluetoothProtocol) -> None:
        if protocol in self._protocols:
            self._protocols.remove(protocol)

    def run_coroutine(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def get_status(self) -> dict:
        return {
            "nuki": {"lock": self._nuki_lock.value, "doorsensor": self._nuki_doorsensor.value},
            "door": {"state": self._door_state.value, "mode": self._door_mode.value},
            "relay": {
                "openclose": self._relay_openclose,
                "openhold": self._relay_openhold,
                "opendoor": self._relay_opendoor,
            },
            "version": self._version,
        }

    def get_jsonrpc_status_notification(self) -> str:
        status = self.get_status()
        return json.dumps({"jsonrpc": "2.0", "method": "status", "params": status})

    def publish_status(self) -> None:
        """Publish status to all connected smartphones."""
        for protocol in self._protocols:
            protocol.send_status()

    def activate(self, client: aiomqtt.Client) -> None:
        self._mqtt = client
        self.run_coroutine(bluetooth_publish_sesami_status(self))

    @property
    def logger(self) -> Logger:
        return self._logger

    @property
    def mqtt(self) -> aiomqtt.Client:
        if self._mqtt is None:
            raise RuntimeError("MQTT client not initialized")
        return self._mqtt

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


async def mqtt_receiver(client: aiomqtt.Client, agent: SesamiBluetoothAgent) -> None:
    async for msg in client.messages:
        payload = msg.payload.decode()
        topic = str(msg.topic)
        agent.logger.info("[mqtt] receive %s=%s", topic, payload)
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


async def activate(logger: Logger, config: SesamiConfig, version: str) -> None:
    agent = SesamiBluetoothAgent(logger, config, version)
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    sock.bind((config.bluetooth_macaddr, config.bluetooth_channel))
    blueserver = await loop.create_server(lambda: SesamiBluetoothProtocol(agent), sock=sock, backlog=config.bluetooth_backlog)

    async with aiomqtt.Client(
        config.mqtt_host, port=config.mqtt_port, username=config.mqtt_username, password=config.mqtt_password
    ) as client:
        agent.activate(client)
        device = agent.nuki_device
        await client.subscribe(f"nuki/{device}/state")
        await client.subscribe(f"nuki/{device}/doorsensorState")
        await client.subscribe(f"sesami/{device}/state")
        await client.subscribe(f"sesami/{device}/mode")
        await client.subscribe(f"sesami/{device}/relay/openclose")
        await client.subscribe(f"sesami/{device}/relay/openhold")
        await client.subscribe(f"sesami/{device}/relay/opendoor")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(mqtt_receiver(client, agent))
            tg.create_task(blueserver.serve_forever())


def main():
    parser = argparse.ArgumentParser(
        prog="nuki-sesami-bluez",
        description="Receive door commands from smartphones via bluetooth and forwards these to sesami-nuki",
        epilog="Belrog: you shall not pass!",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-p", "--prefix", help="runtime system root; e.g. '~/.local' or '/'", type=str, default=None)
    parser.add_argument(
        "-c",
        "--cpath",
        help="configuration path; e.g. '/etc/nuki-sesami' or '~/.config/nuki-sesami'",
        type=str,
        default=None,
    )
    parser.add_argument("-V", "--verbose", help="be verbose", action="store_true")
    parser.add_argument("-v", "--version", help="print version and exit", action="store_true")

    args = parser.parse_args()
    version = importlib.metadata.version("nuki-sesami")
    if args.version:
        print(version)  # noqa: T201
        sys.exit(0)

    prefix = args.prefix or get_prefix()
    cpath = args.cpath or get_config_path()
    logpath = os.path.join(prefix, "var/log/nuki-sesami-bluez")

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger("nuki-sesami-bluez", logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    config = get_config(cpath)

    logger.info("version          : %s", version)
    logger.info("prefix           : %s", prefix)
    logger.info("config-path      : %s", cpath)
    logger.info("nuki.device      : %s", config.nuki_device)
    logger.info("mqtt.host        : %s", config.mqtt_host)
    logger.info("mqtt.port        : %i", config.mqtt_port)
    logger.info("mqtt.username    : %s", config.mqtt_username)
    logger.info("mqtt.password    : %s", "***")
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
