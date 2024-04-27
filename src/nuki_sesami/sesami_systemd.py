import argparse
import logging
import os
import shutil
import subprocess
import sys
from logging import Logger
from logging.handlers import RotatingFileHandler
from nuki_sesami.util import is_virtual_env, getlogger, exec


SYSTEMD_TEMPLATE = '''[Unit]
Description=Electric door controller using a Nuki 3.0 pro smart lock
After=network.target
Wants=Network.target

[Service]
Type=simple
Restart=always
RestartSec=1
Environment=%s
ExecStart=%s %s -H %s -U %s -P %s
StandardError=journal
StandardOutput=journal
StandardInput=null

[Install]
WantedBy=multi-user.target
'''


def nuki_sesami_systemd(logger: Logger, device: str, host: str, username: str, password: str,
                        remove: bool = False)  -> None:
    prefix = sys.prefix if is_virtual_env() else '/'
    systemd_fname = os.path.join(prefix,  'lib/systemd/system/nuki-sesami.service')
    systemctl = ["echo", "/usr/bin/systemctl"] if is_virtual_env() else ["systemctl"]

    if remove:
        exec(systemctl + ["stop", "nuki-sesami"], logger, check=False)
        exec(systemctl + ["disable", "nuki-sesami"], logger, check=False)
        exec(["/usr/bin/rm", "-vrf", systemd_fname], logger, check=False)
        return

    sesami = shutil.which('nuki-sesami')
    if not sesami:
        logger.error("failed to detect 'nuki-sesami' binary")
        sys.exit(1)

    pth = [x for x in sys.path if x.startswith('/home/')]
    env = 'PYTHONPATH=%s:$PYTHONPATH' % pth[0] if len(pth) else ''

    d = os.path.dirname(systemd_fname)
    if not os.path.exists(d):
        os.makedirs(d)

    with open(systemd_fname, 'w+') as f:
        f.write(SYSTEMD_TEMPLATE % (env, sesami, device, host, username, password))
        logger.info("created '%s'", systemd_fname)

    try:
        exec(systemctl + ["daemon-reload"], logger, check=True)
        exec(systemctl + ["enable", "nuki-sesami"], logger, check=True)
        exec(systemctl + ["start", "nuki-sesami"], logger, check=True)
        logger.info("done")
    except subprocess.CalledProcessError:
        logger.exception("failed to install nuki-sesami systemd service")
        sys.exit(1)


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
        logger.debug("username    : %s", args.username)
        logger.debug("password    : ***")
        logger.debug("remove      : %s", args.remove)

    if 'VIRTUAL_ENV' in os.environ:
        logger.info("virtual environment detected, performing dummy installation")

    try:
        nuki_sesami_systemd(logger, args.device, args.host, args.username, args.password, args.remove)
    except KeyboardInterrupt:
        logger.info("program terminated")
    except Exception:
        logger.exception("system daemon installation failed")


if __name__ == "__main__":
    main()
