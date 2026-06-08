from __future__ import annotations

import json
import os
from pydantic import BaseModel, Field, ConfigDict, field_validator

from nuki_sesami.state import PushbuttonLogic


class NukiConfig(BaseModel):
    device: str


class MqttConfig(BaseModel):
    host: str
    port: int
    username: str | None = None
    password: str | None = None


class BluetoothConfig(BaseModel):
    macaddr: str
    channel: int
    backlog: int = 10


class GpioConfig(BaseModel):
    pushbutton: int
    opendoor: int
    openhold_mode: int = Field(alias="openhold-mode")
    openclose_mode: int = Field(alias="openclose-mode")

    model_config = ConfigDict(populate_by_name=True)


class SesamiConfig(BaseModel):
    nuki: NukiConfig
    mqtt: MqttConfig
    bluetooth: BluetoothConfig
    gpio: GpioConfig
    pushbutton: PushbuttonLogic

    # The estimated time, in seconds, for the door to open and close
    door_open_time: int = Field(default=40, alias="door-open-time")

    # The estimated time, in seconds, for the door close when ending openhold mode
    door_close_time: int = Field(default=10, alias="door-close-time")

    # The estimated time, in seconds, for the lock to move from locked or latched to unlatched
    lock_unlatch_time: int = Field(default=4, alias="lock-unlatch-time")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("pushbutton", mode="before")
    @classmethod
    def validate_pushbutton(cls, v: str | int) -> PushbuttonLogic:
        if isinstance(v, str):
            try:
                return PushbuttonLogic[v]
            except KeyError:
                raise ValueError(f"Invalid pushbutton logic: {v}") from None
        return PushbuttonLogic(v)

    @property
    def nuki_device(self) -> str:
        """The hexadecimal Nuki device ID (e.g. 'ABCD1234')"""
        return self.nuki.device

    @property
    def mqtt_host(self) -> str:
        """The MQTT broker host name or IP address"""
        return self.mqtt.host

    @property
    def mqtt_port(self) -> int:
        """The MQTT broker port number (usually 1883)"""
        return self.mqtt.port

    @property
    def mqtt_username(self) -> str | None:
        """The username when connecting to the MQTT broker"""
        return self.mqtt.username

    @property
    def mqtt_password(self) -> str | None:
        """The password when connecting to the MQTT broker"""
        return self.mqtt.password

    @property
    def bluetooth_macaddr(self) -> str:
        """The Bluetooth MAC address"""
        return self.bluetooth.macaddr

    @property
    def bluetooth_channel(self) -> int:
        """The Bluetooth RFCOMM channel number"""
        return self.bluetooth.channel

    @property
    def bluetooth_backlog(self) -> int:
        """The Bluetooth socket backlog size"""
        return self.bluetooth.backlog

    @property
    def gpio_pushbutton(self) -> int:
        """The GPIO pin number for the pushbutton input"""
        return self.gpio.pushbutton

    @property
    def gpio_opendoor(self) -> int:
        """The GPIO pin number for the 'door open' output trigger"""
        return self.gpio.opendoor

    @property
    def gpio_openhold_mode(self) -> int:
        """The GPIO pin number for setting the 'open hold' mode"""
        return self.gpio.openhold_mode

    @property
    def gpio_openclose_mode(self) -> int:
        """The GPIO pin number for setting the 'open close' mode"""
        return self.gpio.openclose_mode


def get_config(prefix: str) -> SesamiConfig:
    """Returns a SesamiConfig instance for the given prefix.

    Arguments:
    * prefix: the prefix for the config file, e.g. '/etc/nuki-sesami'

    Returns:
    * config: SesamiConfig instance
    """
    fname = os.path.join(prefix, "config.json")
    with open(fname) as f:
        config_dict = json.load(f)

    fname = os.path.join(prefix, "auth.json")
    if os.path.exists(fname):
        with open(fname) as f:
            auth_dict = json.load(f)
        config_dict["mqtt"]["username"] = auth_dict.get("username")
        config_dict["mqtt"]["password"] = auth_dict.get("password")

    return SesamiConfig.model_validate(config_dict)
