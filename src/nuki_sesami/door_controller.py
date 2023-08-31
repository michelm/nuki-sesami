#!/bin/env python3

from enum import IntEnum
import argparse
import paho.mqtt.client as mqtt
from gpiozero import Button, DigitalOutputDevice


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


class NukiTrigger(IntEnum):
    system          = 0 # system / bluetooth command
    reserved        = 1
    button          = 2
    automatic       = 3 # e.g. time control
    autolock        = 6
    homekit         = 171
    mqtt            = 172


class DoorTargetState(IntEnum):
    closed      = 1
    open        = 2
    openhold    = 3


def mqtt_on_connect(client, userdata, flags, rc):
    '''The callback for when the client receives a CONNACK response from the server.

    Allways subscribes to topics ensuring subscriptions will be renwed on reconnect.
    '''
    if rc == mqtt.CONNACK_ACCEPTED:
        print(f"[mqtt] connected; code={rc}, flags={flags}")
    else:
        print(f"[mqtt] connect failed; code={rc}, flags={flags}")
    door = userdata
    client.subscribe(f"nuki/{door._nuki_device_id}/state")
    client.subscribe(f"nuki/{door._nuki_device_id}/lockActionEvent")


def mqtt_on_message(client, userdata, msg):
    '''The callback for when a PUBLISH message of Nuki smart lock state is received.
    '''
    try:
        if msg.topic.endswith("/lockActionEvent"):
            event = msg.payload.decode("utf-8")
            print(f"[mqtt] topic={msg.topic}, event={event}")
            door = userdata
            door.process_lock_action_event(event)
        elif msg.topic.endswith("/state"):
            lock = NukiLockState(int(msg.payload))
            print(f"[mqtt] topic={msg.topic}, lock={lock.name}:{lock}")
            door = userdata
            door.process_lock_state(lock)
    except Exception as e:
        print(f"[mqtt] topic={msg.topic}, payload={msg.payload}, payload_type={type(msg.payload)}, payload_length={len(msg.payload)}, exception={e}")


class Relay(DigitalOutputDevice):
    def __init__(self, pin, *args, **kwargs):
        super(Relay, self).__init__(pin, active_high=False, *args, **kwargs)


class PushButton(Button):
    def __init__(self, pin, userdata, *args, **kwargs):
        super(PushButton, self).__init__(pin, *args, **kwargs)
        self.userdata = userdata


def pushbutton_pressed(button):
    print(f"[input] Door (open/hold/close) push button {button.pin} is pressed")
    door = button.userdata
    if door.target == DoorTargetState.openhold:
        door.close()
    elif door.target == DoorTargetState.open:
        door.open(hold=True)
    else:
        door.open()


class ElectricDoor():
    '''Opens an electric door based on the Nuki smart lock state

    Subscribes as client to MQTT door status topic from 'Nuki 3.0 pro' smart lock. When the lock has been opened
    it will activate a relay, e.g. using the 'RPi Relay Board', triggering the electric door to open.
    '''
    def __init__(self, nuki_device_id: str, pushbutton_pin: int, opendoor_pin: int, openhold_mode_pin: int, openclose_mode_pin: int):
        self._nuki_device_id = nuki_device_id
        self._nuki_state = NukiLockState.undefined
        self._nuki_trigger = NukiTrigger.system
        self._mqtt = mqtt.Client()
        self._mqtt.on_connect = mqtt_on_connect
        self._mqtt.on_message = mqtt_on_message
        self._mqtt.user_data_set(self) # pass instance of electricdoor
        self._pushbutton = PushButton(pushbutton_pin, self)
        self._pushbutton.when_pressed = pushbutton_pressed
        self._opendoor = Relay(opendoor_pin) # uses normally open relay (NO)
        self._openhold_mode = Relay(openhold_mode_pin) # uses normally open relay (NO)
        self._openclose_mode = Relay(openclose_mode_pin) # uses normally open relay (NO)
        self._target_state = DoorTargetState.closed

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
    def target(self) -> DoorTargetState:
        return self._target_state

    @target.setter
    def target(self, target: DoorTargetState):
        self._target_state = target

    @property
    def trigger(self) -> NukiTrigger:
        return self._nuki_trigger

    def mode(self, openhold: bool):
        if openhold:
            print(f"[mode] open and hold")
            self._openhold_mode.on()
            self._openclose_mode.off()
        else:
            print(f"[mode] open/close")
            self._openhold_mode.off()
            self._openclose_mode.on()

    def process_lock_state(self, lock: NukiLockState):
        print(f"[process_lock_state] target={self.target.name}:{self.target}, lock={self.lock.name}:{self.lock} -> {lock.name}:{lock}")
        if lock == NukiLockState.unlatched and self.lock == NukiLockState.unlatching:
            if self.target == DoorTargetState.openhold:
                self.mode(openhold=True)
            elif self.target == DoorTargetState.open:
                print(f"[relay] opening door")
                self._opendoor.blink(on_time=1, off_time=1, n=1, background=True)
                self.target = DoorTargetState.closed
        self.lock = lock

    def process_lock_action_event(self, event: str):
        s = event.split(",")
        lock = NukiLockState(int(s[0]))
        trigger = NukiTrigger(int(s[1]))
        if lock == NukiLockState.unlatched and trigger != NukiTrigger.mqtt and self.target == DoorTargetState.closed:
            self.target = DoorTargetState.open
        self._nuki_trigger = trigger

    def lock_action(self, action: NukiLockState):
        print(f"[mqtt] request lock={action.name}:{action}")
        self._nuki_trigger = NukiTrigger.mqtt
        self._mqtt.publish(f"nuki/{self._nuki_device_id}/lockAction", int(action))

    def open(self, hold: bool = False):
        self.target = DoorTargetState.openhold if hold else DoorTargetState.open
        print(f"[open] hold={hold} target={self.target.name}:{self.target}, lock={self.lock.name}:{self.lock}")
        if self.lock not in [NukiLockState.unlatched, NukiLockState.unlatching]:
            self.lock_action(NukiLockState.unlatched)

    def close(self):
        target = DoorTargetState.closed
        print(f"[close] target={target.name}:{target}, lock={self.lock.name}:{self.lock}")
        if self.target == DoorTargetState.openhold:
            if self.lock not in [NukiLockState.unlatched, NukiLockState.unlatching]:
                self.lock_action(NukiLockState.unlatched)
            self.mode(openhold=False)
        self.target = target


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

    if args.verbose:
        print(f"device          : {args.device}")
        print(f"host            : {args.host}")
        print(f"port            : {args.port}")
        print(f"username        : {args.username}")
        print(f"password        : ***")
        print(f"pushbutton      : ${args.pushbutton}")
        print(f"opendoor        : ${args.opendoor}")
        print(f"openhold_mode   : ${args.openhold_mode}")
        print(f"openclose_mode  : ${args.openclose_mode}")

    door = ElectricDoor(args.device, args.pushbutton, args.opendoor, args.openhold_mode, args.openclose_mode)

    try:
        door.activate(args.host, args.port, args.username, args.password)
    except KeyboardInterrupt:
        print("Program terminated")
    except Exception as e:
        print(f"Something went wrong: {e}")


if __name__ == "__main__":
    main()
