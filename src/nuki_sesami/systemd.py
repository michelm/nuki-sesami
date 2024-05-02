import argparse
import json
import logging
import os
import shutil
import stat
import subprocess
import sys
from logging import Logger

from nuki_sesami.util import get_auth_fname, getlogger, is_virtual_env, run

SYSTEMD_TEMPLATE = '''[Unit]
Description=Electric door controller using a Nuki 3.0 pro smart lock
After=network.target
Wants=Network.target

[Service]
Type=simple
Restart=always
RestartSec=1
Environment=%s
ExecStart=%s %s --host=%s --port=%i --auth-file=%s
StandardError=journal
StandardOutput=journal
StandardInput=null

[Install]
WantedBy=multi-user.target
'''


def get_systemctl() -> list[str]:
    return ["echo", "/usr/bin/systemctl"] if is_virtual_env() else ["systemctl"]


def get_systemd_service_fname() -> str:
    prefix = sys.prefix if is_virtual_env() else '/'
    return os.path.join(prefix,  'lib/systemd/system/nuki-sesami.service')


def create_auth_file(logger: Logger, username: str, password: str) -> str:
    fname = get_auth_fname()

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
        json.dump(auth, f)
    logger.info("created '%s'", fname)

    os.chmod(fname, stat.S_IRUSR)
    return fname


def systemd_service_install(logger: Logger, device: str, host: str, port: int, username: str, password: str) -> None:
    sesami = shutil.which('nuki-sesami')
    if not sesami:
        logger.error("failed to detect 'nuki-sesami' binary")
        sys.exit(1)

    pth = [x for x in sys.path if x.startswith('/home/')]
    env = 'PYTHONPATH=%s:$PYTHONPATH' % pth[0] if len(pth) else ''
    fname = get_systemd_service_fname()

    d = os.path.dirname(fname)
    if not os.path.exists(d):
        os.makedirs(d)

    auth = create_auth_file(logger, username, password)

    with open(fname, 'w+') as f:
        f.write(SYSTEMD_TEMPLATE % (env, sesami, device, host, port, auth))
        logger.info("created '%s'", fname)

    systemctl = get_systemctl()

    try:
        run([*systemctl, "daemon-reload"], logger, check=True)
        run([*systemctl, "enable", "nuki-sesami"], logger, check=True)
        run([*systemctl, "start", "nuki-sesami"], logger, check=True)
        logger.info("done")
    except subprocess.CalledProcessError:
        logger.exception("failed to install nuki-sesami systemd service")
        sys.exit(1)


def systemd_service_remove(logger: Logger) -> None:
    fname = get_systemd_service_fname()
    systemctl = get_systemctl()
    run([*systemctl, "stop", "nuki-sesami"], logger, check=False)
    run([*systemctl, "disable", "nuki-sesami"], logger, check=False)
    run(["/usr/bin/rm", "-vrf", fname], logger, check=False)


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami-systemd',
        description='Setup nuki-sesami as systemd service',
        epilog='''The way is shut.
        It was made by those who are Dead, and the Dead keep it, until the time comes.
        The way is shut.''',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument('device',
                        help="nuki hexadecimal device id, e.g. 3807B7EC", type=str)
    parser.add_argument('-H', '--host', help="hostname or IP address of the mqtt broker, e.g. 'mqtt.local'",
                        default='localhost', type=str)
    parser.add_argument('-p', '--port', help="mqtt broker port number", default=1883, type=int)
    parser.add_argument('-U', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')
    parser.add_argument('-R', '--remove', help="Remove nuki-sesami systemd service", action='store_true')

    args = parser.parse_args()
    prefix = sys.prefix if is_virtual_env() else '/'
    logpath = os.path.join(prefix, 'var/log/nuki-sesami-daemon')

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami', logpath, level=logging.DEBUG if args.verbose else logging.INFO)

    if args.verbose:
        logger.debug("device      : %s", args.device)
        logger.debug("host        : %s", args.host)
        logger.debug("port        : %i", args.port)
        logger.debug("username    : %s", args.username)
        logger.debug("password    : ***")
        logger.debug("remove      : %s", args.remove)

    if 'VIRTUAL_ENV' in os.environ:
        logger.info("virtual environment detected, performing dummy installation")

    try:
        if args.remove:
            systemd_service_remove(logger)
        else:
            systemd_service_install(logger, args.device, args.host, args.port, args.username, args.password)
    except KeyboardInterrupt:
        logger.info("program terminated")
    except Exception:
        logger.exception("system daemon installation failed")


if __name__ == "__main__":
    main()
