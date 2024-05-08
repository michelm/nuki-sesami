import argparse
import json
import logging
import os
from logging import Logger
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.reasoncodes import ReasonCode

from nuki_sesami.lock import NukiDoorsensorState, NukiLockState
from nuki_sesami.state import DoorMode, DoorState
from nuki_sesami.util import get_config_path, get_prefix, getlogger
from nuki_sesami.config import SesamiConfig, get_config
from nuki_sesami.clients import SesamiClient, get_clients


def mqtt_on_connect(client: mqtt.Client, userdata: Any, flags: mqtt.ConnectFlags,
                    rcode: ReasonCode, _props):
    '''The callback for when the client receives a CONNACK response from the server.

    Allways subscribes to topics ensuring subscriptions will be renwed on reconnect.
    '''
    sesamibluez = userdata

    if rcode.is_failure:
        sesamibluez.logger.error("(mqtt) connect failed; rcode=%r, flags=%r", rcode, flags)
        return

    sesamibluez.logger.info("(mqtt) connected; rcode=%r, flags=%r", rcode, flags)
    client.subscribe(f"nuki/{sesamibluez.nuki_device}/state")
    client.subscribe(f"nuki/{sesamibluez.nuki_device}/doorsensorState")
    client.subscribe(f"sesami/{sesamibluez.nuki_device}/state") # internal state (debugging)
    client.subscribe(f"sesami/{sesamibluez.nuki_device}/mode")
    client.subscribe(f"sesami/{sesamibluez.nuki_device}/relay/openhold")
    client.subscribe(f"sesami/{sesamibluez.nuki_device}/relay/openclose")
    client.subscribe(f"sesami/{sesamibluez.nuki_device}/relay/opendoor")


def mqtt_on_message(_client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
    '''The callback for when a PUBLISH message of Nuki smart lock state is received.
    '''
    sesamibluez = userdata
    try:
        if msg.topic == f"nuki/{sesamibluez.nuki_device}/state":
            sesamibluez.nuki_lock = NukiLockState(int(msg.payload))
        elif msg.topic == f"nuki/{sesamibluez.nuki_device}/doorsensorState":
            sesamibluez.nuki_doorsensor = NukiDoorsensorState(int(msg.payload))
        elif msg.topic == f"sesami/{sesamibluez.nuki_device}/state":
            sesamibluez.door_state = DoorState(int(msg.payload))
        elif msg.topic == f"sesami/{sesamibluez.nuki_device}/mode":
            sesamibluez.door_mode = DoorMode(int(msg.payload))
        elif msg.topic == f"sesami/{sesamibluez.nuki_device}/relay/openhold":
            sesamibluez.relay_openhold = msg.payload == "1"
        elif msg.topic == f"sesami/{sesamibluez.nuki_device}/relay/openclose":
            sesamibluez.relay_openclose = msg.payload == "1"
        elif msg.topic == f"sesami/{sesamibluez.nuki_device}/relay/opendoor":
            sesamibluez.relay_opendoor = msg.payload == "1"
        else:
            sesamibluez.logger.info("(mqtt) topic=%s, payload=%r, type=%s",
                            msg.topic, msg.payload, type(msg.payload))
    except Exception:
        sesamibluez.logger.exception("(mqtt) topic=%s, payload=%s, payload_type=%s, payload_length=%i",
            msg.topic, msg.payload, type(msg.payload), len(msg.payload)
        )


class SesamiBluez:
    '''Acts as broker between smartphones via bluetooth and the nuki-sesami eletrical door opener via mqtt.

    Subscribes as client to MQTT eletrical door opener topics from 'Nuki Sesami'. Received door commands from
    smartphones are forwarded to the MQTT broker.
    '''
    def __init__(self, logger: Logger, config: SesamiConfig):
        self._logger = logger
        self._nuki_device = config.nuki_device
        self._nuki_lock = NukiLockState.undefined
        self._nuki_doorsensor = NukiDoorsensorState.unknown
        self._door_state = DoorState.openclose1
        self._door_mode = DoorMode.openclose
        self._relay_openclose = False
        self._relay_openhold = False
        self._relay_opendoor = False
        self._mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._mqtt.on_connect = mqtt_on_connect
        self._mqtt.on_message = mqtt_on_message
        self._mqtt.user_data_set(self) # pass instance of bluetooth broker
        self._mqtt_host = config.mqtt_host
        self._mqtt_port = config.mqtt_port
        self._bluetooth_macaddr = config.bluetooth_macaddr
        self._bluetooth_port = config.bluetooth_port

    def activate(self, username: str, password: str):
        '''Activates the electric door bluetooth broker.

        Start listening on incoming bluetooth connections, connects to MQTT broker and
        subscribes to nuki smartlock / door state topics.

        Parameters:
        * username: MQTT username
        * password: MQTT password
        '''

        # TODO: start listening on incoming blueooth connections

        if username and password:
            self._mqtt.username_pw_set(username, password)
        self._mqtt.connect(self._mqtt_host, self._mqtt_port, 60)
        self._mqtt.loop_forever()

    def publish_status(self):
        '''Publish status to all connected smartphones on bluetooth'''
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
        self.logger.info("(bluez) status=%s", status)

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
    clients = get_clients(cpath)

    logger.debug("prefix          : %s", prefix)
    logger.debug("config-path     : %s", cpath)
    logger.info("nuki-device      : %s", config.nuki_device)
    logger.info("mqtt-host        : %s", config.mqtt_host)
    logger.info("mqtt-port        : %i", config.mqtt_port)
    logger.info("mqtt-username    : %s", config.mqtt_username)
    logger.info("bluetooth.macaddr: %s", config.bluetooth_macaddr)
    logger.info("bluetooth.port   : %i", config.bluetooth_port)
    logger.info("clients          : %i", len(clients))
    for client in clients:
        logger.debug("client           : mac(%s), pubkey(%s)", client.macaddr, client.pubkey)

    sesamibluez = SesamiBluez(logger, config)

    try:
        sesamibluez.activate(config.mqtt_username, config.mqtt_password)
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
