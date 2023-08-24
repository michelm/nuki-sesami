#!/bin/env python3

from enum import IntEnum
import argparse
import paho.mqtt.client as mqtt


class NukiDoorState(IntEnum):
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


def on_connect(client, userdata, flags, rc):
    '''The callback for when the client receives a CONNACK response from the server.

    Allways subscribes to topics ensuring subscriptions will be renwed on reconnect.
    '''
    if rc == mqtt.CONNACK_ACCEPTED:
        print(f"[mqtt] connected; code={rc}, flags={flags}")
    else:
        print(f"[mqtt] connect failed; code={rc}, flags={flags}")
    door = userdata
    client.subscribe(f"nuki/{door.nuki_device_id}/state")


def on_message(client, userdata, msg):
    '''The callback for when a PUBLISH message of Nuki door state is received from the server.
    '''
    print(f"[mqtt] topic={msg.topic}, payload={msg.payload}, payload_type={type(msg.payload)}, payload_length={len(msg.payload)}")
    nuki_state = NukiDoorState(int(msg.payload))
    door = userdata

    if nuki_state == NukiDoorState.unlatched and door.nuki_state == NukiDoorState.unlatching:
        door.open()

    door.nuki_state = nuki_state


class DoorController():
    '''Opens an electric door based on the Nuki smart lock state

    Subscribes as client to MQTT door status topic from 'Nuki 3.0 pro' smart lock. When the lock has been opened
    it will activate a relay, e.g. using the 'RPi Relay Board', triggering the electric door to open.
    '''
    def __init__(self, nuki_device_id: str, mqtt_host: str, mqtt_port: int):
        self.nuki_device_id = nuki_device_id
        self.nuki_state = NukiDoorState.undefined
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.client = mqtt.Client()
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        self.client.user_data_set(self) # pass instance of doorcontroller

    def activate(self, username: str or None, password: str or None):
        if username and password:
            self.client.username_pw_set(username, password)
        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        self.client.loop_forever()

    def open(self):
        print(f"[relay] opening door")
        # TODO: trigger door open relay
        pass


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
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')

    args = parser.parse_args()

    if args.verbose:
        print(f"device   : {args.device}")
        print(f"host     : {args.host}")
        print(f"port     : {args.port}")
        print(f"username : {args.username}")
        print(f"password : ***")

    door = DoorController(args.device, args.host, args.port)

    try:
        door.activate(args.username, args.password)
    except KeyboardInterrupt:
        print("Program terminated")
    except Exception as e:
        print(f"Something went wrong: {e}")


if __name__ == "__main__":
    main()
