import json
import os

from nuki_sesami.state import PushbuttonLogic


class SesamiConfig:
    def __init__(self, config: dict, auth: dict):
        self._nuki_device = config['nuki']['device']
        self._mqtt_host = config['mqtt']['host']
        self._mqtt_port = config['mqtt']['port']
        self._mqtt_username = auth['username']
        self._mqtt_password = auth['password']
        self._bluetooth_macaddr = config['bluetooth']['macaddr']
        self._bluetooth_port = config['bluetooth']['port']
        self._gpio_pushbutton = config['gpio']['pushbutton']
        self._gpio_opendoor = config['gpio']['opendoor']
        self._gpio_openhold_mode = config['gpio']['openhold-mode']
        self._gpio_openclose_mode = config['gpio']['openclose-mode']
        self._pushbutton = PushbuttonLogic[config['pushbutton']]

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
    def bluetooth_port(self) -> int:
        return self._bluetooth_port

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
