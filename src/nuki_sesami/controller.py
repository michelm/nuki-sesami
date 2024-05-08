import argparse
import logging
import os
from logging import Logger
from typing import Any

import paho.mqtt.client as mqtt
from gpiozero import Button, DigitalOutputDevice
from paho.mqtt.reasoncodes import ReasonCode

from nuki_sesami.config import SesamiConfig, get_config
from nuki_sesami.lock import NukiDoorsensorState, NukiLockAction, NukiLockState
from nuki_sesami.state import DoorMode, DoorRequestState, DoorState, PushbuttonLogic, next_door_state
from nuki_sesami.util import get_config_path, get_prefix, getlogger


def mqtt_on_connect(client: mqtt.Client, userdata: Any, flags: mqtt.ConnectFlags,
                    rcode: ReasonCode, _props):
    '''The callback for when the client receives a CONNACK response from the server.

    Allways subscribes to topics ensuring subscriptions will be renwed on reconnect.
    '''
    door = userdata

    if rcode.is_failure:
        door.logger.error("(mqtt) connect failed; rcode=%r, flags=%r", rcode, flags)
        return

    door.logger.info("(mqtt) connected; rcode=%r, flags=%r", rcode, flags)
    client.subscribe(f"nuki/{door.nuki_device}/state")
    client.subscribe(f"nuki/{door.nuki_device}/doorsensorState")
    mode = door.mode
    client.publish(f"sesami/{door.nuki_device}/state", int(door.state), retain=True) # internal state (debugging)
    client.publish(f"sesami/{door.nuki_device}/mode", int(mode), retain=True)
    client.publish(f"sesami/{door.nuki_device}/relay/openhold", int(mode == DoorMode.openhold), retain=True)
    client.publish(f"sesami/{door.nuki_device}/relay/openclose", int(mode != DoorMode.openhold), retain=True)
    client.publish(f"sesami/{door.nuki_device}/relay/opendoor", 0)
    client.subscribe(f"sesami/{door.nuki_device}/request/state") # == DoorRequestState


def mqtt_on_message(_client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
    '''The callback for when a PUBLISH message of Nuki smart lock state is received.
    '''
    door = userdata
    try:
        if msg.topic == f"nuki/{door.nuki_device}/state":
            lock = NukiLockState(int(msg.payload))
            door.logger.info("(mqtt) topic=%s, lock=%s:%i", msg.topic, lock.name, int(lock))
            door.on_lock_state(lock)
        elif msg.topic == f"nuki/{door.nuki_device}/doorsensorState":
            sensor = NukiDoorsensorState(int(msg.payload))
            door.logger.info("(mqtt) topic=%s, sensor=%s:%i", msg.topic, sensor.name, int(sensor))
            door.on_doorsensor_state(sensor)
        elif msg.topic == f"sesami/{door.nuki_device}/request/state":
            request = DoorRequestState(int(msg.payload))
            door.logger.info("(mqtt) topic=%s, request=%s:%i", msg.topic, request.name, int(request))
            door.on_door_request(request)
        else:
            door.logger.info("(mqtt) topic=%s, payload=%r, type=%s",
                            msg.topic, msg.payload, type(msg.payload))
    except Exception:
        door.logger.exception("(mqtt) topic=%s, payload=%s, payload_type=%s, payload_length=%i",
            msg.topic, msg.payload, type(msg.payload), len(msg.payload)
        )

class Relay(DigitalOutputDevice):
    def __init__(self, pin, active_high):
        super().__init__(pin, active_high=active_high)


class PushButton(Button):
    def __init__(self, pin, userdata, *args, **kwargs):
        super().__init__(pin, *args, **kwargs)
        self.userdata = userdata


def pushbutton_pressed(button):
    door = button.userdata
    door.logger.info("(input) door (open/hold/close) push button %i is pressed", button.pin)
    door.on_pushbutton_pressed()


class ElectricDoor:
    '''Opens an electric door based on the Nuki smart lock state

    Subscribes as client to MQTT door status topic from 'Nuki 3.0 pro' smart lock. When the lock has been opened
    it will activate a relay, e.g. using the 'RPi Relay Board', triggering the electric door to open.
    '''
    def __init__(self, logger: Logger, config: SesamiConfig):
        self._logger = logger
        self._nuki_device = config.nuki_device
        self._nuki_state = NukiLockState.undefined
        self._nuki_doorsensor = NukiDoorsensorState.unknown
        self._mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._mqtt.on_connect = mqtt_on_connect
        self._mqtt.on_message = mqtt_on_message
        self._mqtt.user_data_set(self) # pass instance of electricdoor
        self._mqtt_host = config.mqtt_host
        self._mqtt_port = config.mqtt_port
        self._pushbutton = PushButton(config.gpio_pushbutton, self)
        self._pushbutton.when_pressed = pushbutton_pressed
        self._opendoor = Relay(config.gpio_opendoor, False) # uses normally open relay (NO)
        self._openhold_mode = Relay(config.gpio_openhold_mode, False) # uses normally open relay (NO)
        self._openclose_mode = Relay(config.gpio_openclose_mode, False) # uses normally open relay (NO)
        self._state = DoorState.openclose1

    def activate(self, username: str, password: str):
        '''Activates the electric door logic.

        Initializes GPIO to pins to default state, connects to MQTT broker and
        subscribes to nuki smartlock topics.

        Parameters:
        * username: MQTT username
        * password: MQTT password
        '''
        self._opendoor.off()
        self.mode = DoorMode.openclose
        self.state = DoorState.openclose1
        if username and password:
            self._mqtt.username_pw_set(username, password)
        self._mqtt.connect(self._mqtt_host, self._mqtt_port, 60)
        self._mqtt.loop_forever()

    @property
    def lock(self) -> NukiLockState:
        return self._nuki_state

    @lock.setter
    def lock(self, state: NukiLockState):
        self._nuki_state = state

    @property
    def sensor(self) -> NukiDoorsensorState:
        return self._nuki_doorsensor

    @sensor.setter
    def sensor(self, state: NukiDoorsensorState):
        self._nuki_doorsensor = state

    @property
    def openhold(self) -> bool:
        return self._state == DoorState.openhold

    @property
    def state(self) -> DoorState:
        return self._state

    @state.setter
    def state(self, state: DoorState):
        if state == self._state:
            return
        self.logger.info("(state) %s -> %s", self._state.name, state.name)
        self._state = state
        self._mqtt.publish(f"sesami/{self.nuki_device}/state", int(state), retain=True)

    @property
    def logger(self) -> Logger:
        return self._logger

    @property
    def nuki_device(self) -> str:
        return self._nuki_device

    @property
    def mode(self) -> DoorMode:
        return DoorMode.openhold if self.openhold else DoorMode.openclose

    @mode.setter
    def mode(self, mode: DoorMode):
        openhold = (mode == DoorMode.openhold)
        if openhold:
            self._openhold_mode.on()
            self._openclose_mode.off()
        else:
            self._openhold_mode.off()
            self._openclose_mode.on()
        self.logger.info("(mode) open%s", "hold" if openhold else "close")
        self._mqtt.publish(f"sesami/{self.nuki_device}/relay/openhold", int(openhold), retain=True)
        self._mqtt.publish(f"sesami/{self.nuki_device}/relay/openclose", int(not openhold), retain=True)
        self._mqtt.publish(f"sesami/{self.nuki_device}/mode", int(mode), retain=True)

    def lock_action(self, action: NukiLockAction):
        self.logger.info("(lock) request action=%s:%i", action.name, int(action))
        self._mqtt.publish(f"nuki/{self.nuki_device}/lockAction", int(action))

    def open(self):
        self.logger.info("(open) state={self.state.name}:{self.state}, lock={self.lock.name}:{self.lock}")
        if self.lock not in [NukiLockState.unlatched, NukiLockState.unlatching]:
            self.lock_action(NukiLockAction.unlatch)

    def close(self):
        self.logger.info("(close) state=%s:%i, lock=%s:%i", self.state.name, self.state, self.lock.name, self.lock)
        if self.lock not in [NukiLockState.unlatched, NukiLockState.unlatching,
                             NukiLockState.unlocked, NukiLockState.unlocked2]:
            self.lock_action(NukiLockAction.unlock)
        self.mode = DoorMode.openclose

    def on_lock_state(self, lock: NukiLockState):
        self.logger.info("(lock_state) state=%s:%i, lock=%s:%i -> %s:%i",
                         self.state.name, self.state, self.lock.name, self.lock, lock.name, lock)
        if self.lock == NukiLockState.unlatching and lock == NukiLockState.unlatched:
            if self.openhold:
                self.mode = DoorMode.openhold
            else:
                self.logger.info("(relay) opening door")
                self._opendoor.blink(on_time=1, off_time=1, n=1, background=True)
                self._mqtt.publish(f"sesami/{self.nuki_device}/relay/opendoor", 1)
        elif lock not in [NukiLockState.unlatched, NukiLockState.unlatching] and self.state == DoorState.openclose2:
            self.state = DoorState.openclose1
        self.lock = lock

    def on_doorsensor_state(self, sensor: NukiDoorsensorState):
        self.logger.info("(doorsensor_state) state=%s:%i, sensor=%s:%i -> %s:%i",
                         self.state.name, self.state, self.sensor.name, self.sensor, sensor.name, sensor)
        self.sensor = sensor

    def on_door_request(self, request: DoorRequestState):
        '''Process a requested door state received from the MQTT broker.

        The Door request state is used to open/close the door and/or hold the door
        open based on the current door state and mode.

        Request processing logic:
        - open
            * if door is closed then open the door
            * if door is in openhold mode then ignore the request
        - close:
            * if door is in openhold mode then close the door
        - openhold:
            * if door is not open then open it and keep it open
            * ignore request if already in openhold mode
        - none:
            * ignore request

        Parameters:
        * request: the requested door state
        '''
        self.logger.info("(door_request) state=%s:%i, lock=%s:%i, request=%s:%i",
                         self.state.name, self.state, self.lock.name, self.lock, request.name, request)
        if request == DoorRequestState.none:
            return
        if request == DoorRequestState.open:
            if self.state == DoorState.openclose1:
                self.state = DoorState.openclose2
                self.open()
        elif request == DoorRequestState.close:
            if self.state == DoorState.openhold:
                self.state = DoorState.openclose1
                self.close()
        elif request == DoorRequestState.openhold and self.state != DoorState.openhold:
            self.state = DoorState.openhold
            self.open()

    def on_pushbutton_pressed(self):
        pass # defined in derived classes


class ElectricDoorPushbuttonOpenHold(ElectricDoor):
    '''Electric door with pushbutton 'open and hold' logic

    When pressing the pushbutton the door will be opened and held open until the pushbutton is pressed again.
    '''
    def __init__(self, logger: logging.Logger, config: SesamiConfig):
        super().__init__(logger, config)

    def on_pushbutton_pressed(self):
        self.state = DoorState.openhold if self.state == DoorState.openclose1 else DoorState.openclose1
        self.logger.info("(pushbutton_pressed) state=%s:%i, lock=%s:%i",
                         self.state.name, self.state, self.lock.name, self.lock)
        if self.state == DoorState.openhold:
            self.open()
        else:
            self.close()


class ElectricDoorPushbuttonOpen(ElectricDoor):
    '''Electric door with pushbutton open logic

    When pressing the pushbutton the door will be opened for a few seconds after which it will be closed again.
    '''
    def __init__(self, logger: logging.Logger, config: SesamiConfig):
        super().__init__(logger, config)

    def on_pushbutton_pressed(self):
        self.logger.info("(pushbutton_pressed) state=%s:%i, lock=%s:%i",
                         self.state.name, self.state, self.lock.name, self.lock)
        self.open()


class ElectricDoorPushbuttonToggle(ElectricDoor):
    '''Electric door with pushbutton toggle logic

    When pressing the pushbutton the door will open, if during the smart lock unlatching
    phase of the pushbutton is pressed again the door will be held open until the pushbutton
    is pressed again.
    '''
    def __init__(self, logger: logging.Logger, config: SesamiConfig):
        super().__init__(logger, config)

    def on_pushbutton_pressed(self):
        self.state = next_door_state(self._state)
        self.logger.info("(pushbutton_pressed) state=%s:%s, lock=%s:%s",
                         self.state.name, self.state, self.lock.name, self.lock)
        if self.state == DoorState.openclose1:
            self.close()
        elif self.state == DoorState.openclose2:
            self.open()
        elif self.state == DoorState.openhold:
            pass # no action here


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami',
        description='Open and close an electric door equipped with a Nuki 3.0 pro smart lock',
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
    logpath = os.path.join(prefix, 'var/log/nuki-sesami')

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami', logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    config = get_config(cpath)

    logger.debug("prefix        : %s", prefix)
    logger.debug("config-path   : %s", cpath)
    logger.info("nuki-device    : %s", config.nuki_device)
    logger.info("mqtt-host      : %s", config.mqtt_host)
    logger.info("mqtt-port      : %i", config.mqtt_port)
    logger.info("mqtt-username  : %s", config.mqtt_username)
    logger.info("gpio-pushbutton: %s", config.gpio_pushbutton)
    logger.info("gpio-opendoor  : %s", config.gpio_opendoor)
    logger.info("gpio-openhold  : %s", config.gpio_openhold_mode)
    logger.info("gpio-openclose : %s", config.gpio_openclose_mode)
    logger.info("pushbutton     : %s", config.pushbutton.name)

    if config.pushbutton == PushbuttonLogic.open:
        door = ElectricDoorPushbuttonOpen(logger, config)
    elif config.pushbutton == PushbuttonLogic.toggle:
        door = ElectricDoorPushbuttonToggle(logger, config)
    else:
        door = ElectricDoorPushbuttonOpenHold(logger, config)

    try:
        door.activate(config.mqtt_username, config.mqtt_password)
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
