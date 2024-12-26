from nuki_sesami.config import SesamiConfig
from nuki_sesami.state import PushbuttonLogic


def test_sesami_config():
    config = {
        "nuki": {
            "device": "12345678",
        },
        "mqtt": {
            "host": "mqtt.example.com",
            "port": 1883,
        },
        "bluetooth": {
            "macaddr": "11:22:33:44:55:66",
            "channel": 1,
        },
        "gpio": {
            "pushbutton": 17,
            "opendoor": 18,
            "openhold-mode": 22,
            "openclose-mode": 23,
        },
        "pushbutton": PushbuttonLogic.openhold.name,
        "door-open-time": 40,
        "door-close-time": 10,
        "lock-unlatch-time": 4,
    }

    auth = {
        "username": "mqttuser",
        "password": "mqttpass",
    }

    sesami_config = SesamiConfig(config, auth)

    assert sesami_config.nuki_device == "12345678"
    assert sesami_config.mqtt_host == "mqtt.example.com"
    assert sesami_config.mqtt_port == 1883
    assert sesami_config.mqtt_username == "mqttuser"
    assert sesami_config.mqtt_password == "mqttpass"
    assert sesami_config.bluetooth_macaddr == "11:22:33:44:55:66"
    assert sesami_config.bluetooth_channel == 1
    assert sesami_config.bluetooth_backlog == 10
    assert sesami_config.gpio_pushbutton == 17
    assert sesami_config.gpio_opendoor == 18
    assert sesami_config.gpio_openhold_mode == 22
    assert sesami_config.gpio_openclose_mode == 23
    assert sesami_config.pushbutton == PushbuttonLogic.openhold
    assert sesami_config.door_open_time == 40
    assert sesami_config.door_close_time == 10
    assert sesami_config.lock_unlatch_time == 4
