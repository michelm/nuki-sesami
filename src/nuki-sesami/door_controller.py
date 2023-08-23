#!/bin/env python3

import argparse
import paho.mqtt.client as mqtt

def on_connect(client, userdata, flags, rc):
    '''The callback for when the client receives a CONNACK response from the server.

    Allways subscribes to topics ensuring subscriptions will be renwed on reconnect.
    '''
    print(f"Connected with result code {rc}")

    # TODO: define/add actual topic(s)
    client.subscribe("$SYS/#")

def on_message(client, userdata, msg):
    '''The callback for when a PUBLISH message is received from the server.
    '''
    print(f"{msg.topic} {msg.payload}")


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

    def activate(self, username: str or None = None, password: str or None = None):
        if username and password:
            # TODO: set user credentials
            pass
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
    parser.add_argument('-u', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)

    args = parser.parse_args()
    host = args.host
    port = args.port
    username = args.username
    password = args.password

    print(f"host : {host}")
    print(f"port : {port}")
    print(f"username : {username}")
    print(f"password : {password}")


def dummy():
    host = "mqtt.local"
    port = 1883
    username = None
    password = None
    door = DoorController(host, port)

    try:
        door.activate(username, password)
    except KeyboardInterrupt:
        print("Program terminated")
    else:
        print("Something went wrong")


if __name__ == "__main__":
    main()
