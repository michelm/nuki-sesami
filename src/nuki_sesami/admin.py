import argparse
import importlib.metadata
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
from logging import Logger

from nuki_sesami.error import SesamiArgError
from nuki_sesami.state import PushbuttonLogic
from nuki_sesami.util import get_config_path, get_prefix, getlogger, run

SYSTEMD_TEMPLATE = '''[Unit]
Description=%s
After=network.target
Wants=Network.target

[Service]
Type=simple
Restart=always
RestartSec=1
ExecStart=%s -c %s
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


def get_systemctl(dryrun: bool) -> list[str]:
    if dryrun:
        return ["echo", "/usr/bin/systemctl"]
    if os.geteuid() == 0:
        return ["systemctl"]
    return ["sudo", "systemctl"]


def get_systemd_service_fname(prefix: str, name: str) -> str:
    return os.path.join(prefix, f'lib/systemd/system/{name}.service')


def create_config_file(logger: Logger, cpath: str, args: argparse.Namespace) -> None:
    '''Creates a config file for nuki-sesami services

    Write nuki lock device id, mqtt broker host and port, and bluetooth settings
    to configuration file (<prefix>/nuki-sesami/config.json)

    Parameters:
    * logger: Logger, the logger
    * args: argparse.Namespace, the command line arguments
    '''
    if not args.device:
        a = ['-d', '--device']
        raise SesamiArgError(a)

    if not args.blue_macaddr:
        a = ['-m', '--blue-macaddr']
        raise SesamiArgError(a)

    fname = os.path.join(cpath, 'config.json')

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
            'channel': args.blue_channel,
            'backlog': args.blue_backlog
        },
        'gpio': {
            'pushbutton': args.gpio_pushbutton,
            'opendoor': args.gpio_opendoor,
            'openhold-mode': args.gpio_openhold,
            'openclose-mode': args.gpio_openclose
        },
        'pushbutton': args.pushbutton,
        'door-open-time': args.door_open_time,
        'lock-unlatch-time': args.lock_unlatch_time
    }

    if os.path.exists(fname):
        os.unlink(fname)

    with open(fname, 'w+') as f:
        json.dump(config, f, indent=2)
    os.chmod(fname, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    logger.info("created '%s'", fname)


def create_auth_file(logger: Logger, cpath: str, username: str, password: str) -> None:
    '''Creates an auth file for nuki-sesami

    The file contains the MQTT username and password.

    Parameters:
    * logger: Logger, the logger
    * username: str, the MQTT username
    * password: str, the MQTT password
    '''
    if not username:
        a = ['-U', '--username']
        raise SesamiArgError(a)

    if not password:
        a = ['-P', '--password']
        raise SesamiArgError(a)

    fname = os.path.join(cpath, 'auth.json')

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


def create_clients_file(logger: Logger, cpath: str) -> None:
    '''Creates a (bluetooth) clients file for nuki-sesami services

    The file contains a list of bluetooth clients. Each entry consists of
    a the client's mac address and a public key used by that client when
    signing messages.

    Parameters:
    * logger: Logger, the logger
    '''
    fname = os.path.join(cpath, 'clients.json')
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


def create_systemd_service(logger: Logger, prefix: str, cpath: str, name: str, dryrun: bool) -> None:
    '''Creates and start a systemd service for nuki-sesami

    Creates the systemd service file, reloads the systemd daemon and
    starts the service.

    Parameters:
    * logger: Logger, the logger
    * prefix: str, the system root; e.g. '/'
    * cpath: str, the configuration path; e.g. '/etc/nuki-sesami'
    * name: str, the service name
    * dryrun: bool, if True, the service is not created
    '''
    prog = shutil.which(name)
    if not prog:
        logger.error("failed to detect '%s' binary", name)
        sys.exit(1)

    fname = get_systemd_service_fname(prefix, name)

    d = os.path.dirname(fname)
    if not os.path.exists(d):
        os.makedirs(d)

    with open(fname, 'w+') as f:
        f.write(SYSTEMD_TEMPLATE % (SYSTEMD_DESCRIPTION[name], prog, cpath))
        logger.info("created '%s'", fname)

    if not dryrun:
        src = fname
        dst = get_systemd_service_fname('/', name)
        if dst != src:
            cmd = ['mv'] if os.geteuid() == 0 else ['sudo', 'mv']
            run([*cmd, '-v', '-f', src, dst], logger, check=True)

    systemctl = get_systemctl(dryrun)

    try:
        run([*systemctl, "daemon-reload"], logger, check=True)
        run([*systemctl, "enable", name], logger, check=True)
        run([*systemctl, "start", name], logger, check=True)
        logger.info("done")
    except subprocess.CalledProcessError:
        logger.exception("failed to install %s systemd service", name)
        sys.exit(1)


def services_install(logger: Logger, prefix: str, cpath: str, args: argparse.Namespace) -> None:
    '''Create nuki-sesami config files and installs systemd services

    Parameters:
    * logger: Logger, the logger
    * prefix: str, the system root; e.g. '/'
    * cpath: str, the configuration path; e.g. '/etc/nuki-sesami'
    * args: argparse.Namespace, the command line arguments
    '''
    create_config_file(logger, cpath, args)
    create_auth_file(logger, cpath, args.username, args.password)
    create_clients_file(logger, cpath)
    create_systemd_service(logger, prefix, cpath, 'nuki-sesami', args.dryrun)
    create_systemd_service(logger, prefix, cpath, 'nuki-sesami-bluez', args.dryrun)


def systemd_service_remove(logger: Logger, prefix: str, systemctl: list[str], name: str) -> None:
    '''Removes a systemd service
    '''
    run([*systemctl, "stop", name], logger, check=False)
    run([*systemctl, "disable", name], logger, check=False)
    fname = get_systemd_service_fname(prefix, name)
    run(["/usr/bin/rm", "-vrf", fname], logger, check=False)


def services_remove(logger: Logger, prefix: str, dryrun: bool) -> None:
    '''Removes all nuki-sesami related systemd services
    '''
    systemctl = get_systemctl(dryrun)
    systemd_service_remove(logger, prefix, systemctl, 'nuki-sesami')
    systemd_service_remove(logger, prefix, systemctl, 'nuki-sesami-bluez')
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
    parser.add_argument('-c', '--cpath',
                        help="configuration path; e.g. '/etc/nuki-sesami' or '~/.config/nuki-sesami'",
                        type=str, default=None)
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
    parser.add_argument('-b', '--blue-channel', help="bluetooth agent listen channel", default=4, type=int)
    parser.add_argument('-n', '--blue-backlog', help="bluetooth maximum number of clients", default=10, type=int)
    parser.add_argument('-1', '--gpio-pushbutton',
                        help="pushbutton door/hold open request (gpio)pin", default=2, type=int)
    parser.add_argument('-2', '--gpio-opendoor', help="door open relay (gpio)pin", default=26, type=int)
    parser.add_argument('-3', '--gpio-openhold', help="door open and hold mode relay (gpio)pin", default=20, type=int)
    parser.add_argument('-4', '--gpio-openclose', help="door open/close mode relay (gpio)pin", default=21, type=int)
    parser.add_argument('-B', '--pushbutton', help="pushbutton logic when pressed",
                        default=PushbuttonLogic.openhold.name,
                        choices=[x.name for x in PushbuttonLogic],
                        type=str)
    parser.add_argument('-O', '--door-open-time', help="door open time when in 'normal' openclose mode", default=30, type=int)
    parser.add_argument('-L', '--lock-unlatch-time', help="lock unlatch time", default=15, type=int)
    parser.add_argument('-R', '--dryrun', help="dummy systemd installation", action='store_true')
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')
    parser.add_argument('-v', '--version', help="print version and exit", action='store_true')

    args = parser.parse_args()
    version = importlib.metadata.version('nuki-sesami')
    if args.version:
        print(version)
        sys.exit(0)

    prefix = get_prefix()
    cpath = args.cpath or get_config_path()
    logpath = os.path.join(prefix, 'var/log/nuki-sesami-setup')

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami-setup', logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    logger.debug("version           : %s", version)
    logger.debug("action            : %s", args.action)
    logger.debug("pushbutton        : %s", PushbuttonLogic[args.pushbutton].name)
    logger.debug("door-open-time    : %i", args.door_open_time)
    logger.debug("lock-unlatch-time : %i", args.lock_unlatch_time)
    logger.debug("nuki.device       : %s", args.device)
    logger.debug("mqtt.host         : %s", args.host)
    logger.debug("mqtt.port         : %i", args.port)
    logger.debug("mqtt.username     : %s", args.username)
    logger.debug("mqtt.password     : ***")
    logger.debug("bluetooth.macaddr : %s", args.blue_macaddr)
    logger.debug("bluetooth.channel : %i", args.blue_channel)
    logger.debug("bluetooth.backlog : %i", args.blue_backlog)
    logger.debug("gpio.pushbutton   : %s", args.gpio_pushbutton)
    logger.debug("gpio.opendoor     : %s", args.gpio_opendoor)
    logger.debug("gpio.openhold     : %s", args.gpio_openhold)
    logger.debug("gpio.openclose    : %s", args.gpio_openclose)
    logger.debug("dryrun            : %s", args.dryrun)

    if 'VIRTUAL_ENV' in os.environ:
        logger.info("virtual environment detected, performing dummy installation")

    try:
        if args.action == 'remove':
            services_remove(logger, prefix, args.dryrun)
        else:
            services_install(logger, prefix, cpath, args)
    except KeyboardInterrupt:
        logger.info("program terminated")
    except Exception:
        logger.exception("admin action(%s) failed", args.action)


if __name__ == "__main__":
    main()
