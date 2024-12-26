import os

from nuki_sesami.admin import get_systemctl, get_systemd_service_fname


def test_get_systemctl():
    assert get_systemctl(True) == ["echo", "/usr/bin/systemctl"]
    assert get_systemctl(False) == ["systemctl"] if os.geteuid() == 0 else ["sudo", "systemctl"]


def test_get_systemd_service_fname():
    assert get_systemd_service_fname("/", "nuki-sesami") == "/lib/systemd/system/nuki-sesami.service"
    assert get_systemd_service_fname("/usr", "nuki-sesami-bluez") == "/usr/lib/systemd/system/nuki-sesami-bluez.service"
