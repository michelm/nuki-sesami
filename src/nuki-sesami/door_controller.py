#!/bin/env python3

import argparse
import paho.mqtt.client as mqtt


def on_connect(client, userdata, flags, rc):
    '''The callback for when the client receives a CONNACK response from the server.

    Allways subscribes to topics ensuring subscriptions will be renwed on reconnect.
    '''
    # TODO: add proper error handling
    print(f"Connected with result code {rc}")

    # TODO: define/add actual topic(s)
    client.subscribe("$SYS/#")


def on_message(client, userdata, msg):
    '''The callback for when a PUBLISH message is received from the server.
    '''
    print(f"{msg.topic} {msg.payload}")
    # TODO: get door status from topic, trigger open relay when needed


class DoorController():
    '''Opens an electric door based on the Nuki smart lock state

    Subscribes as client to MQTT door status topic from 'Nuki 3.0 pro' smart lock. When the lock has been opened
    it will activate a relay, e.g. using the 'RPi Relay Board', triggering the electric door to open.
    '''
    def __init__(self, host: str, port: int = 1883):
        self.host = host
        self.port = port
        self.client = mqtt.Client()
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        self.client.user_data_set(self) # pass instance of doorcontroller

    def activate(self, username: str or None, password: str or None):
        if username and password:
            self.client.username_pw_set(username, password)
        self.client.connect(self.host, self.port, 60)
        self.client.loop_forever()


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami',
        description='Opens an electric door when a Nuki 3.0 pro smart lock has been opened',
        epilog='Belrog: you shall not pass!'
    )
    parser.add_argument('host', help="hostname or IP address of the mqtt broker, e.g. 'mqtt' or 'mqtt.local'")
    parser.add_argument('-p', '--port', help="mqtt broker port number", default=1883, type=int)
    parser.add_argument('-U', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')

    args = parser.parse_args()

    if args.verbose:
        print(f"host     : {args.host}")
        print(f"port     : {args.port}")
        print(f"username : {args.username}")
        print(f"password : ***")

    door = DoorController(args.host, args.port)

    try:
        door.activate(args.username, args.password)
    except KeyboardInterrupt:
        print("Program terminated")
    except Exception as e:
        print(f"Something went wrong: {e}")


if __name__ == "__main__":
    main()
