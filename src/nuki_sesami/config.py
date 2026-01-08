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
    door_open_time: int = Field(default=40, alias="door-open-time")
    door_close_time: int = Field(default=10, alias="door-close-time")
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
        return self.nuki.device

    @property
    def mqtt_host(self) -> str:
        return self.mqtt.host

    @property
    def mqtt_port(self) -> int:
        return self.mqtt.port

    @property
    def mqtt_username(self) -> str | None:
        return self.mqtt.username

    @property
    def mqtt_password(self) -> str | None:
        return self.mqtt.password

    @property
    def bluetooth_macaddr(self) -> str:
        return self.bluetooth.macaddr

    @property
    def bluetooth_channel(self) -> int:
        return self.bluetooth.channel

    @property
    def bluetooth_backlog(self) -> int:
        return self.bluetooth.backlog

    @property
    def gpio_pushbutton(self) -> int:
        return self.gpio.pushbutton

    @property
    def gpio_opendoor(self) -> int:
        return self.gpio.opendoor

    @property
    def gpio_openhold_mode(self) -> int:
        return self.gpio.openhold_mode

    @property
    def gpio_openclose_mode(self) -> int:
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
