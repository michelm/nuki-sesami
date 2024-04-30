import argparse
import json
import logging
import os
import sys
from enum import IntEnum
from logging import Logger
from typing import Any

import paho.mqtt.client as mqtt
from gpiozero import Button, DigitalOutputDevice
from paho.mqtt.reasoncodes import ReasonCode

from nuki_sesami.door_state import DoorMode, DoorRequestState, DoorState, next_door_state
from nuki_sesami.util import getlogger, is_virtual_env


class NukiLockState(IntEnum):
    uncalibrated    = 0 # untrained
    locked          = 1 # online
    unlocking       = 2
    unlocked        = 3 # rto active
    locking         = 4
    unlatched       = 5 # open
    unlocked2       = 6 # lock-n-go
    unlatching      = 7 # opening
    boot_run        = 253
    motor_blocked   = 254
    undefined       = 255


class NukiLockAction(IntEnum):
    unlock          = 1 # activate rto
    lock            = 2 # deactivate rto
    unlatch         = 3 # electric strike actuation
    lock_and_go1    = 4 # lock&go; activate continuous mode
    lock_and_go2    = 5 # lock&go with unlatch deactivate continuous mode
    full_lock       = 6
    fob             = 80 # (without action) fob (without action)
    button          = 90 # (without action) button (without action)


class NukiDoorsensorState(IntEnum):
    deactivated         = 1 # door sensor not used
    door_closed         = 2
    door_opened         = 3
    door_state_unknown  = 4
    calibrating         = 5
    uncalibrated        = 16
    tampered            = 240
    unknown             = 255


class PushbuttonLogic(IntEnum):
    openhold    = 0
    open        = 1
    toggle      = 2 # toggle between 'open' and 'openhold' door modes


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
    client.subscribe(f"nuki/{door.nuki_device_id}/state")
    client.subscribe(f"nuki/{door.nuki_device_id}/doorsensorState")
    mode = door.mode
    client.publish(f"sesami/{door.nuki_device_id}/state", int(door.state), retain=True) # internal state (debugging)
    client.publish(f"sesami/{door.nuki_device_id}/mode", int(mode), retain=True)
    client.publish(f"sesami/{door.nuki_device_id}/relay/openhold", int(mode == DoorMode.openhold), retain=True)
    client.publish(f"sesami/{door.nuki_device_id}/relay/openclose", int(mode != DoorMode.openhold), retain=True)
    client.publish(f"sesami/{door.nuki_device_id}/relay/opendoor", 0)
    client.subscribe(f"sesami/{door.nuki_device_id}/request/state") # == DoorRequestState


def mqtt_on_message(_client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
    '''The callback for when a PUBLISH message of Nuki smart lock state is received.
    '''
    door = userdata
    try:
        if msg.topic == f"nuki/{door.nuki_device_id}/state":
            lock = NukiLockState(int(msg.payload))
            door.logger.info("(mqtt) topic=%s, lock=%s:%i", msg.topic, lock.name, int(lock))
            door.on_lock_state(lock)
        elif msg.topic == f"nuki/{door.nuki_device_id}/doorsensorState":
            sensor = NukiDoorsensorState(int(msg.payload))
            door.logger.info("(mqtt) topic=%s, sensor=%s:%i", msg.topic, sensor.name, int(sensor))
            door.on_doorsensor_state(sensor)
        elif msg.topic == f"sesami/{door.nuki_device_id}/request/state":
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
    def __init__(self, logger: Logger, nuki_device_id: str,
                 pushbutton_pin: int, opendoor_pin: int, openhold_mode_pin: int, openclose_mode_pin: int):
        self._logger = logger
        self._nuki_device_id = nuki_device_id
        self._nuki_state = NukiLockState.undefined
        self._nuki_doorsensor = NukiDoorsensorState.unknown
        self._mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._mqtt.on_connect = mqtt_on_connect
        self._mqtt.on_message = mqtt_on_message
        self._mqtt.user_data_set(self) # pass instance of electricdoor
        self._pushbutton = PushButton(pushbutton_pin, self)
        self._pushbutton.when_pressed = pushbutton_pressed
        self._opendoor = Relay(opendoor_pin, False) # uses normally open relay (NO)
        self._openhold_mode = Relay(openhold_mode_pin, False) # uses normally open relay (NO)
        self._openclose_mode = Relay(openclose_mode_pin, False) # uses normally open relay (NO)
        self._state = DoorState.openclose1

    def activate(self, host: str, port: int, username: str, password: str):
        self._opendoor.off()
        self.mode = DoorMode.openclose
        self.state = DoorState.openclose1
        if username and password:
            self._mqtt.username_pw_set(username, password)
        self._mqtt.connect(host, port, 60)
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
        self._mqtt.publish(f"sesami/{self.nuki_device_id}/state", int(state), retain=True)

    @property
    def logger(self) -> Logger:
        return self._logger

    @property
    def nuki_device_id(self) -> str:
        return self._nuki_device_id

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
        self._mqtt.publish(f"sesami/{self.nuki_device_id}/relay/openhold", int(openhold), retain=True)
        self._mqtt.publish(f"sesami/{self.nuki_device_id}/relay/openclose", int(not openhold), retain=True)
        self._mqtt.publish(f"sesami/{self.nuki_device_id}/mode", int(mode), retain=True)

    def lock_action(self, action: NukiLockAction):
        self.logger.info("(lock) request action=%s:%i", action.name, int(action))
        self._mqtt.publish(f"nuki/{self.nuki_device_id}/lockAction", int(action))

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
                self._mqtt.publish(f"sesami/{self.nuki_device_id}/relay/opendoor", 1)
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
    def __init__(self, *arg, **kwargs):
        super().__init__(*arg, **kwargs)

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
    def __init__(self, *arg, **kwargs):
        super().__init__(*arg, **kwargs)

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
    def __init__(self, *arg, **kwargs):
        super().__init__(*arg, **kwargs)

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


def get_username_password(auth_file: str, username: str, password: str) -> tuple[str, str]:
    '''Returns the (mqtt) username and password from the auth_file or the command line arguments.

    If username and/or password are not provided; i.e. are None, and the auth_file
    exists then the username and password from the auth_file will be used and returned.

    Parameters:
    * auth_file: str, the file name containing the username and password
    * username: str, the username from the command line arguments
    * password: str, the password from the command line arguments

    Returns:
    * username: str, the username
    * password: str, the password
    '''
    if not os.path.exists(auth_file):
        return username, password

    with open(auth_file) as f:
        auth = json.load(f)

    if username is None:
        username = auth['username']
    if password is None:
        password = auth['password']

    return username, password


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami',
        description='Open and close an electric door equipped with a Nuki 3.0 pro smart lock',
        epilog='Belrog: you shall not pass!',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('device', help="nuki hexadecimal device id, e.g. 3807B7EC", type=str)
    parser.add_argument('-H', '--host',
        help="hostname or IP address of the mqtt broker, e.g. 'mqtt.local'", default='localhost', type=str)
    parser.add_argument('-p', '--port', help="mqtt broker port number", default=1883, type=int)
    parser.add_argument('-U', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)
    parser.add_argument('-A', '--auth-file', help="secrets file name", default='/etc/nuki-sesami/auth.json', type=str)
    parser.add_argument('-1', '--pushbutton', help="pushbutton door/hold open request (gpio)pin", default=2, type=int)
    parser.add_argument('-2', '--opendoor', help="door open relay (gpio)pin", default=26, type=int)
    parser.add_argument('-3', '--openhold-mode', help="door open and hold mode relay (gpio)pin", default=20, type=int)
    parser.add_argument('-4', '--openclose-mode', help="door open/close mode relay (gpio)pin", default=21, type=int)
    parser.add_argument('-B', '--buttonlogic', help="pushbutton logic when pressed; 0=openhold,1=open,2=toggle",
                        default=int(PushbuttonLogic.openhold), type=int)
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')

    args = parser.parse_args()
    logpath = os.path.join(sys.prefix, 'var/log/nuki-sesami') if is_virtual_env() else '/var/log/nuki-sesami'

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami', logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    logger.debug("args.device=%s", args.device)
    logger.debug("args.host=%s", args.host)
    logger.debug("args.port=%s", args.port)
    logger.debug("args.username=%s", args.username)
    logger.debug("args.password=***")
    logger.debug("args.auth-file=%s", args.auth_file)
    logger.debug("args.pushbutton=%s", args.pushbutton)
    logger.debug("args.opendoor=%s", args.opendoor)
    logger.debug("args.openhold-mode=%s", args.openhold_mode)
    logger.debug("args.openclose-mode=%s", args.openclose_mode)
    logger.debug("args.buttonlogic=%s", args.buttonlogic)

    try:
        buttonlogic = PushbuttonLogic(args.buttonlogic)
    except ValueError:
        logger.exception("invalid (push)button logic; --buttonlogic=%r", args.buttonlogic)
        sys.exit(1)

    if buttonlogic == PushbuttonLogic.open:
        door = ElectricDoorPushbuttonOpen(logger, args.device, args.pushbutton, args.opendoor, args.openhold_mode,
                                          args.openclose_mode)
    elif buttonlogic == PushbuttonLogic.toggle:
        door = ElectricDoorPushbuttonToggle(logger, args.device, args.pushbutton, args.opendoor, args.openhold_mode,
                                            args.openclose_mode)
    else:
        door = ElectricDoorPushbuttonOpenHold(logger, args.device, args.pushbutton, args.opendoor, args.openhold_mode,
                                              args.openclose_mode)

    username, password = get_username_password(args.auth_file, args.username, args.password)

    try:
        door.activate(args.host, args.port, username, password)
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
