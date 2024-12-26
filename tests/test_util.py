import os
import sys

from nuki_sesami.util import get_config_path, get_prefix, is_virtual_env


def test_is_virtual_env():
    assert is_virtual_env() == (sys.prefix != sys.base_prefix)


def test_get_prefix():
    prefix = get_prefix()
    if os.geteuid() == 0:
        assert prefix == "/"
    elif is_virtual_env():
        assert prefix == sys.prefix
    else:
        assert prefix == os.path.join(os.path.expanduser("~"), ".local")


def test_get_config_path():
    path = get_config_path()
    if os.geteuid() == 0:
        assert path == "/etc/nuki-sesami"
    elif is_virtual_env():
        assert path == os.path.join(sys.prefix, "etc", "nuki-sesami")
    else:
        assert path == os.path.join(os.path.expanduser("~"), ".config", "nuki-sesami")
