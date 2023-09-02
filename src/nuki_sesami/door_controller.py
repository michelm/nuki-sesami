#!/bin/env python3

from enum import IntEnum
import os
import sys
import logging
from logging import Logger
from logging.handlers import RotatingFileHandler
import argparse
import paho.mqtt.client as mqtt
from gpiozero import Button, DigitalOutputDevice
from nuki_sesami.door_state import DoorState, next_door_state


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


def mqtt_on_connect(client, userdata, flags, rc):
    '''The callback for when the client receives a CONNACK response from the server.

    Allways subscribes to topics ensuring subscriptions will be renwed on reconnect.
    '''
    door = userdata
    if rc == mqtt.CONNACK_ACCEPTED:
        door.logger.info(f"(mqtt) connected; code={rc}, flags={flags}")
    else:
        door.logger.error(f"(mqtt) connect failed; code={rc}, flags={flags}")
    client.subscribe(f"nuki/{door._nuki_device_id}/state")


def mqtt_on_message(client, userdata, msg):
    '''The callback for when a PUBLISH message of Nuki smart lock state is received.
    '''
    door = userdata    
    try:
        lock = NukiLockState(int(msg.payload))
        door.logger.info(f"(mqtt) topic={msg.topic}, lock={lock.name}:{lock}")
        door.on_lock_state_changed(lock)
    except Exception as e:
        door.logger.error(f"(mqtt) topic={msg.topic}, payload={msg.payload}, payload_type={type(msg.payload)}, payload_length={len(msg.payload)}, exception={e}")


class Relay(DigitalOutputDevice):
    def __init__(self, pin, *args, **kwargs):
        super(Relay, self).__init__(pin, active_high=False, *args, **kwargs)


class PushButton(Button):
    def __init__(self, pin, userdata, *args, **kwargs):
        super(PushButton, self).__init__(pin, *args, **kwargs)
        self.userdata = userdata


def pushbutton_pressed(button):
    door = button.userdata
    door.logger.info(f"(input) door (open/hold/close) push button {button.pin} is pressed")
    door.on_pushbutton_pressed()


class ElectricDoor():
    '''Opens an electric door based on the Nuki smart lock state

    Subscribes as client to MQTT door status topic from 'Nuki 3.0 pro' smart lock. When the lock has been opened
    it will activate a relay, e.g. using the 'RPi Relay Board', triggering the electric door to open.
    '''
    def __init__(self, logger: Logger, nuki_device_id: str, pushbutton_pin: int, opendoor_pin: int, openhold_mode_pin: int, openclose_mode_pin: int):
        self._logger = logger
        self._nuki_device_id = nuki_device_id
        self._nuki_state = NukiLockState.undefined
        self._mqtt = mqtt.Client()
        self._mqtt.on_connect = mqtt_on_connect
        self._mqtt.on_message = mqtt_on_message
        self._mqtt.user_data_set(self) # pass instance of electricdoor
        self._pushbutton = PushButton(pushbutton_pin, self)
        self._pushbutton.when_pressed = pushbutton_pressed
        self._opendoor = Relay(opendoor_pin) # uses normally open relay (NO)
        self._openhold_mode = Relay(openhold_mode_pin) # uses normally open relay (NO)
        self._openclose_mode = Relay(openclose_mode_pin) # uses normally open relay (NO)
        self._state = DoorState.openclose1

    def activate(self, host: str, port: int, username: str or None, password: str or None):
        self._opendoor.off()
        self._openhold_mode.off()
        self._openclose_mode.on()
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
    def openhold(self) -> bool:
        return self._state == DoorState.openhold

    @property
    def state(self) -> DoorState:
        return self._state

    @property
    def logger(self) -> Logger:
        return self._logger

    def mode(self, openhold: bool):
        if openhold:
            self.logger.info(f"(mode) open and hold")
            self._openhold_mode.on()
            self._openclose_mode.off()
        else:
            self.logger.info(f"(mode) open/close")
            self._openhold_mode.off()
            self._openclose_mode.on()

    def lock_action(self, action: NukiLockState):
        self.logger.info(f"(lock) request action={action.name}:{action}")
        self._mqtt.publish(f"nuki/{self._nuki_device_id}/lockAction", int(action))

    def open(self):
        self.logger.info(f"(open) state={self.state.name}:{self.state}, lock={self.lock.name}:{self.lock}")
        if self.lock not in [NukiLockState.unlatched, NukiLockState.unlatching]:
            self.lock_action(NukiLockState.unlatched)

    def close(self):
        self.logger.info(f"(close) state={self.state.name}:{self.state}, lock={self.lock.name}:{self.lock}")
        if self.lock not in [NukiLockState.unlatched, NukiLockState.unlatching, NukiLockState.unlocked, NukiLockState.unlocked2]:
            self.lock_action(NukiLockState.unlocked)
        self.mode(openhold=False)

    def on_lock_state_changed(self, lock: NukiLockState):
        self.logger.info(f"(lock_state_changed) state={self.state.name}:{self.state}, lock={self.lock.name}:{self.lock} -> {lock.name}:{lock}")
        if lock == NukiLockState.unlatched and self.lock == NukiLockState.unlatching:
            if self.openhold:
                self.mode(openhold=True)
            else:
                self.logger.info(f"(relay) opening door")
                self._opendoor.blink(on_time=1, off_time=1, n=1, background=True)
        elif lock not in [NukiLockState.unlatched, NukiLockState.unlatching] and self.state == DoorState.openclose2:
            self._state = DoorState.openclose1
        self.lock = lock

    def on_pushbutton_pressed(self):
        self._state = next_door_state(self._state)
        self.logger.info(f"(pushbutton_pressed) state={self.state.name}:{self.state}, lock={self.lock.name}:{self.lock}")
        if self.state == DoorState.openclose1:
            self.close()
        elif self.state == DoorState.openclose2:
            self.open()
        elif self.state == DoorState.openhold:
            pass # no action here


def getlogger(name: str, path: str, level: int = logging.INFO) -> Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    handler = RotatingFileHandler(f'{os.path.join(path,name)}.log', maxBytes=1048576, backupCount=10)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    return logger


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami',
        description='Open and close an electric door equipped with a Nuki 3.0 pro smart lock',
        epilog='Belrog: you shall not pass!',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('device', help="nuki hexadecimal device id, e.g. 3807B7EC", type=str)
    parser.add_argument('-H', '--host', help="hostname or IP address of the mqtt broker, e.g. 'mqtt.local'", default='localhost', type=str)
    parser.add_argument('-p', '--port', help="mqtt broker port number", default=1883, type=int)
    parser.add_argument('-U', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)
    parser.add_argument('-1', '--pushbutton', help="pushbutton door/hold open request (gpio)pin", default=2, type=int)
    parser.add_argument('-2', '--opendoor', help="door open relay (gpio)pin", default=26, type=int)
    parser.add_argument('-3', '--openhold_mode', help="door open and hold mode relay (gpio)pin", default=20, type=int)
    parser.add_argument('-4', '--openclose_mode', help="door open/close mode relay (gpio)pin", default=21, type=int)
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')

    args = parser.parse_args()

    logpath = '/var/log/nuki-sesami'
    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami', logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    logger.debug(f"args.device={args.device}")
    logger.debug(f"args.host={args.host}")
    logger.debug(f"args.port={args.port}")
    logger.debug(f"args.username={args.username}")
    logger.debug(f"args.password=***")
    logger.debug(f"args.pushbutton=${args.pushbutton}")
    logger.debug(f"args.opendoor=${args.opendoor}")
    logger.debug(f"args.openhold_mode=${args.openhold_mode}")
    logger.debug(f"args.openclose_mode=${args.openclose_mode}")

    door = ElectricDoor(logger, args.device, args.pushbutton, args.opendoor, args.openhold_mode, args.openclose_mode)

    try:
        door.activate(args.host, args.port, args.username, args.password)
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception as e:
        logger.error(f"something went wrong, exception; {e}")


if __name__ == "__main__":
    main()
