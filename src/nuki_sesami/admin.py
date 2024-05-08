import argparse
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
from logging import Logger

from nuki_sesami.state import PushbuttonLogic
from nuki_sesami.util import get_config_path, get_prefix, getlogger, is_virtual_env, run

SYSTEMD_TEMPLATE = '''[Unit]
Description=%s
After=network.target
Wants=Network.target

[Service]
Type=simple
Restart=always
RestartSec=1
Environment=%s
ExecStart=%s
StandardError=journal
StandardOutput=journal
StandardInput=null

[Install]
WantedBy=multi-user.target
'''

SYSTEMD_DESCRIPTION = {
    'nuki-sesami':
        'Electric door controller using a Nuki 3.0 pro smart lock',
    'nuki-sesami-bluez':
        'Receives commands from Smartphones and forwards them to the Electric door controller (nuki-sesami)'
}


def get_systemctl() -> list[str]:
    return ["echo", "/usr/bin/systemctl"] if is_virtual_env() else ["systemctl"]


def get_systemd_service_fname(name: str) -> str:
    return os.path.join(get_prefix(), f'lib/systemd/system/{name}.service')


def create_config_file(logger: Logger, args: argparse.Namespace) -> None:
    '''Creates a config file for nuki-sesami services

    Write nuki lock device id, mqtt broker host and port, and bluetooth settings
    to configuration file (<prefix>/nuki-sesami/config.json)

    Parameters:
    * logger: Logger, the logger
    * args: argparse.Namespace, the command line arguments
    '''
    if not args.device:
        raise Exception("missing nuki device identifer argument(-d | --device)")

    if not args.blue_macaddr:
        raise Exception("missing bluetooth mac (listen) address argument(-m | --blue-macaddr)")

    fname = os.path.join(get_config_path(), 'config.json')

    d = os.path.dirname(fname)
    if not os.path.exists(d):
        os.makedirs(d)

    config = {
        'nuki': {
            'device': args.device
        },
        'mqtt': {
            'host': args.host,
            'port': args.port,
        },
        'bluetooth': {
            'macaddr': args.blue_macaddr,
            'port': args.blue_port
        },
        'gpio': {
            'pushbutton': args.gpio_pushbutton,
            'opendoor': args.gpio_opendoor,
            'openhold-mode': args.gpio_openhold,
            'openclose-mode': args.gpio_openclose
        },
        'pushbutton': args.pushbutton
    }

    if os.path.exists(fname):
        os.unlink(fname)

    with open(fname, 'w+') as f:
        json.dump(config, f, indent=2)
    os.chmod(fname, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    logger.info("created '%s'", fname)


def create_auth_file(logger: Logger, username: str, password: str) -> None:
    '''Creates an auth file for nuki-sesami

    The file contains the MQTT username and password.

    Parameters:
    * logger: Logger, the logger
    * username: str, the MQTT username
    * password: str, the MQTT password
    '''
    if not username:
        raise Exception("missing mqtt username argument(-U | --username)")

    if not password:
        raise Exception("missing mqtt password argument(-P | --password)")

    fname = os.path.join(get_config_path(), 'auth.json')

    d = os.path.dirname(fname)
    if not os.path.exists(d):
        os.makedirs(d)

    auth = {
        'username': username,
        'password': password
    }

    if os.path.exists(fname):
        os.unlink(fname)

    with open(fname, 'w+') as f:
        json.dump(auth, f, indent=2)
    os.chmod(fname, stat.S_IRUSR)
    logger.info("created '%s'", fname)


def create_clients_file(logger: Logger) -> None:
    '''Creates a (bluetooth) clients file for nuki-sesami services

    The file contains a list of bluetooth clients. Each entry consists of
    a the client's mac address and a public key used by that client when
    signing messages.

    Parameters:
    * logger: Logger, the logger
    '''
    fname = os.path.join(get_config_path(), 'clients.json')
    if os.path.exists(fname):
        return

    d = os.path.dirname(fname)
    if not os.path.exists(d):
        os.makedirs(d)

    clients = [
        {
            'macaddr': '00:00:00:00:00:00',
            'pubkey': ''
        }
    ]

    with open(fname, 'w+') as f:
        json.dump(clients, f, indent=2)
    os.chmod(fname, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    logger.info("created '%s'", fname)


def create_systemd_service(logger: Logger, name: str) -> None:
    '''Creates and start a systemd service for nuki-sesami

    Creates the systemd service file, reloads the systemd daemon and
    starts the service.

    Parameters:
    * logger: Logger, the logger
    * name: str, the service name
    '''
    prog = shutil.which(name)
    if not prog:
        logger.error("failed to detect '%s' binary", name)
        sys.exit(1)

    pth = [x for x in sys.path if x.startswith('/home/')]
    env = 'PYTHONPATH=%s:$PYTHONPATH' % pth[0] if len(pth) else ''
    fname = get_systemd_service_fname(name)

    d = os.path.dirname(fname)
    if not os.path.exists(d):
        os.makedirs(d)

    with open(fname, 'w+') as f:
        f.write(SYSTEMD_TEMPLATE % (SYSTEMD_DESCRIPTION[name], env, prog))
        logger.info("created '%s'", fname)

    systemctl = get_systemctl()

    try:
        run([*systemctl, "daemon-reload"], logger, check=True)
        run([*systemctl, "enable", name], logger, check=True)
        run([*systemctl, "start", name], logger, check=True)
        logger.info("done")
    except subprocess.CalledProcessError:
        logger.exception("failed to install %s systemd service", name)
        sys.exit(1)


def services_install(logger: Logger, args: argparse.Namespace) -> None:
    '''Create nuki-sesami config files and installs systemd services

    Parameters:
    * logger: Logger, the logger
    * args: argparse.Namespace, the command line arguments
    '''
    create_config_file(logger, args)
    create_auth_file(logger, args.username, args.password)
    create_clients_file(logger)
    create_systemd_service(logger, 'nuki-sesami')
    create_systemd_service(logger, 'nuki-sesami-bluez')


def systemd_service_remove(logger: Logger, systemctl: list[str], name: str) -> None:
    '''Removes a systemd service
    '''
    run([*systemctl, "stop", name], logger, check=False)
    run([*systemctl, "disable", name], logger, check=False)
    fname = get_systemd_service_fname(name)
    run(["/usr/bin/rm", "-vrf", fname], logger, check=False)


def services_remove(logger: Logger) -> None:
    '''Removes all nuki-sesami related systemd services
    '''
    systemctl = get_systemctl()
    systemd_service_remove(logger, systemctl, 'nuki-sesami')
    systemd_service_remove(logger, systemctl, 'nuki-sesami-bluez')
    run([*systemctl, "daemon-reload"], logger, check=True)


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami-admin',
        description='Setup or remove nuki-sesami configuration and systemd services',
        epilog='''The way is shut.
        It was made by those who are Dead, and the Dead keep it, until the time comes.
        The way is shut.''',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument('action', help="Setup or remove nuki-sesami systemd service",
                        choices=['setup', 'remove'])

    parser.add_argument('-d', '--device',
                        help="nuki hexadecimal device id, e.g. 3807B7EC", type=str, default=None)
    parser.add_argument('-H', '--host',
                        help="hostname or IP address of the mqtt broker, e.g. 'mqtt.local'",
                        default='localhost', type=str)
    parser.add_argument('-p', '--port', help="mqtt broker port number", default=1883, type=int)
    parser.add_argument('-U', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)
    parser.add_argument('-m', '--blue-macaddr',
                        help="bluetooth mac address to listen on, e.g. 'B8:27:EB:B9:2A:F0'",
                        type=str, default=None)
    parser.add_argument('-b', '--blue-port', help="bluetooth broker port number", default=3, type=int)
    parser.add_argument('-1', '--gpio-pushbutton', help="pushbutton door/hold open request (gpio)pin", default=2, type=int)
    parser.add_argument('-2', '--gpio-opendoor', help="door open relay (gpio)pin", default=26, type=int)
    parser.add_argument('-3', '--gpio-openhold', help="door open and hold mode relay (gpio)pin", default=20, type=int)
    parser.add_argument('-4', '--gpio-openclose', help="door open/close mode relay (gpio)pin", default=21, type=int)
    parser.add_argument('-B', '--pushbutton', help="pushbutton logic when pressed",
                        default=PushbuttonLogic.openhold.name,
                        choices=[x.name for x in PushbuttonLogic],
                        type=str)
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')

    args = parser.parse_args()
    logpath = os.path.join(get_prefix(), 'var/log/nuki-sesami-setup')

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami-setup', logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    logger.debug("action            : %s", args.action)
    logger.debug("device            : %s", args.device)
    logger.debug("host              : %s", args.host)
    logger.debug("port              : %i", args.port)
    logger.debug("username          : %s", args.username)
    logger.debug("password          : ***")
    logger.debug("blue-macaddr      : %s", args.blue_macaddr)
    logger.debug("blue-port         : %i", args.blue_port)
    logger.debug("gpio-pushbutton   : %s", args.gpio_pushbutton)
    logger.debug("gpio-opendoor     : %s", args.gpio_opendoor)
    logger.debug("gpio-openhold     : %s", args.gpio_openhold)
    logger.debug("gpio-openclose    : %s", args.gpio_openclose)
    logger.debug("pushbutton        : %s", PushbuttonLogic[args.pushbutton].name)

    if 'VIRTUAL_ENV' in os.environ:
        logger.info("virtual environment detected, performing dummy installation")

    try:
        if args.action == 'remove':
            services_remove(logger)
        else:
            services_install(logger, args)
    except KeyboardInterrupt:
        logger.info("program terminated")
    except Exception:
        logger.exception("admin action(%s) failed", args.action)


if __name__ == "__main__":
    main()
