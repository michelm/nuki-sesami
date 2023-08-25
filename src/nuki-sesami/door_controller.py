#!/bin/env python3

from enum import IntEnum
import argparse
import paho.mqtt.client as mqtt
from gpiozero import Button, LED


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
    if rc == mqtt.CONNACK_ACCEPTED:
        print(f"[mqtt] connected; code={rc}, flags={flags}")
    else:
        print(f"[mqtt] connect failed; code={rc}, flags={flags}")
    door = userdata
    client.subscribe(f"nuki/{door.nuki_device_id}/state")


def mqtt_on_message(client, userdata, msg):
    '''The callback for when a PUBLISH message of Nuki smart lock state is received.
    '''
    print(f"[mqtt] topic={msg.topic}, payload={msg.payload}, payload_type={type(msg.payload)}, payload_length={len(msg.payload)}")
    door = userdata
    door.process_lock_state(NukiLockState(int(msg.payload)))


class Relay(LED):
    def __init__(self, pin, *args, **kwargs):
        super(Relay, self).__init__(pin, active_high=False, *args, **kwargs)


class PushButton(Button):
    def __init__(self, pin, userdata, *args, **kwargs):
        super(PushButton, self).__init__(pin, *args, **kwargs)
        self.userdata = userdata


def request_door_open(button):
    print(f"[input] Door open push button {button.pin} is pressed")
    door = button.userdata
    door.open()


class ElectricDoor():
    '''Opens an electric door based on the Nuki smart lock state

    Subscribes as client to MQTT door status topic from 'Nuki 3.0 pro' smart lock. When the lock has been opened
    it will activate a relay, e.g. using the 'RPi Relay Board', triggering the electric door to open.
    '''
    def __init__(self, nuki_device_id: str, mqtt_host: str, mqtt_port: int, dooropen: int, pushbutton: int):
        self.nuki_device_id = nuki_device_id
        self.nuki_state = NukiLockState.undefined
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt = mqtt.Client()
        self.mqtt.on_connect = mqtt_on_connect
        self.mqtt.on_message = mqtt_on_message
        self.mqtt.user_data_set(self) # pass instance of electricdoor
        self.button = PushButton(pushbutton, self)
        self.button.when_pressed = request_door_open
        self.relay = Relay(dooropen)
        self.relay.off()

    def activate(self, username: str or None, password: str or None):
        if username and password:
            self.mqtt.username_pw_set(username, password)
        self.mqtt.connect(self.mqtt_host, self.mqtt_port, 60)
        self.mqtt.loop_forever()

    def process_lock_state(self, nuki_state: NukiLockState):
        if nuki_state == NukiLockState.unlatched and self.nuki_state == NukiLockState.unlatching:
            print(f"[relay] opening door")
            self.relay.blink(on_time=1, off_time=1, n=1, background=True)
        self.nuki_state = nuki_state

    def open(self):
        if self.nuki_state != NukiLockState.unlatched and self.nuki_state != NukiLockState.unlatching:
            print(f"[mqtt] request lock unlatched")
            self.mqtt.publish(f"nuki/{self.nuki_device_id}/lockAction", int(NukiLockState.unlatched))


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami',
        description='Opens an electric door when a Nuki 3.0 pro smart lock has been opened',
        epilog='Belrog: you shall not pass!'
    )
    parser.add_argument('device', help="nuki hexadecimal device id, e.g. 3807B7EC", type=str)
    parser.add_argument('-H', '--host', help="hostname or IP address of the mqtt broker, e.g. 'mqtt.local'", default='localhost', type=str)
    parser.add_argument('-p', '--port', help="mqtt broker port number", default=1883, type=int)
    parser.add_argument('-U', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)
    parser.add_argument('-1', '--opendoor', help="door open relay (gpio)pin", default=26, type=int)
    parser.add_argument('-2', '--pushbutton', help="pushbutton door open request (gpio)pin", default=2, type=int)
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')

    args = parser.parse_args()

    if args.verbose:
        print(f"device      : {args.device}")
        print(f"host        : {args.host}")
        print(f"port        : {args.port}")
        print(f"username    : {args.username}")
        print(f"password    : ***")
        print(f"opendoor    : ${args.opendoor}")
        print(f"pushbutton  : ${args.pushbutton}")

    door = ElectricDoor(args.device, args.host, args.port, args.dooropen, args.pushbutton)

    try:
        door.activate(args.username, args.password)
    except KeyboardInterrupt:
        print("Program terminated")
    except Exception as e:
        print(f"Something went wrong: {e}")


if __name__ == "__main__":
    main()
