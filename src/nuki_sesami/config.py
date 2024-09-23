import json
import os

from nuki_sesami.state import PushbuttonLogic


class SesamiConfig:
    def __init__(self, config: dict, auth: dict):
        nuki = config['nuki']
        self._nuki_device = nuki['device']

        mqtt = config['mqtt']
        self._mqtt_host = mqtt['host']
        self._mqtt_port = mqtt['port']
        self._mqtt_username = auth['username']
        self._mqtt_password = auth['password']

        bluetooth = config['bluetooth']
        self._bluetooth_macaddr = bluetooth['macaddr']
        self._bluetooth_channel = bluetooth['channel']
        self._bluetooth_backlog = bluetooth['backlog'] if 'backlog' in bluetooth else 10

        gpio = config['gpio']
        self._gpio_pushbutton = gpio['pushbutton']
        self._gpio_opendoor = gpio['opendoor']
        self._gpio_openhold_mode = gpio['openhold-mode']
        self._gpio_openclose_mode = gpio['openclose-mode']
        self._pushbutton = PushbuttonLogic[config['pushbutton']]
        self._door_open_time = config['door-open-time'] if 'door-open-time' in config else 30
        self._lock_unlatch_time = config['lock-unlatch-time'] if 'lock-unlatch-time' in config else 15

    @property
    def nuki_device(self) -> str:
        return self._nuki_device

    @property
    def mqtt_host(self) -> str:
        return self._mqtt_host

    @property
    def mqtt_port(self) -> int:
        return self._mqtt_port

    @property
    def mqtt_username(self) -> str:
        return self._mqtt_username

    @property
    def mqtt_password(self) -> str:
        return self._mqtt_password

    @property
    def bluetooth_macaddr(self) -> str:
        return self._bluetooth_macaddr

    @property
    def bluetooth_channel(self) -> int:
        return self._bluetooth_channel

    @property
    def bluetooth_backlog(self) -> int:
        return self._bluetooth_backlog

    @property
    def gpio_pushbutton(self) -> int:
        return self._gpio_pushbutton

    @property
    def gpio_opendoor(self) -> int:
        return self._gpio_opendoor

    @property
    def gpio_openhold_mode(self) -> int:
        return self._gpio_openhold_mode

    @property
    def gpio_openclose_mode(self) -> int:
        return self._gpio_openclose_mode

    @property
    def pushbutton(self) -> PushbuttonLogic:
        return self._pushbutton

    @property
    def door_open_time(self) -> int:
        return self._door_open_time

    @property
    def lock_unlatch_time(self) -> int:
        return self._lock_unlatch_time


def get_config(prefix: str) -> SesamiConfig:
    '''Returns a SesamiConfig instance for the given prefix.

    Parameters:
    * prefix: the prefix for the config file, e.g. '/etc/nuki-sesami'

    Returns:
    * config: SesamiConfig instance
    '''
    fname = os.path.join(prefix, 'config.json')
    with open(fname) as f:
        config = json.load(f)

    fname = os.path.join(prefix, 'auth.json')
    with open(fname) as f:
        auth = json.load(f)

    return SesamiConfig(config, auth)
