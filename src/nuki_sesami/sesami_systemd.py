import argparse
import logging
import os
import shutil
import subprocess
import sys
from logging import Logger
from logging.handlers import RotatingFileHandler

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
    systemd_fname = '/lib/systemd/system/nuki-sesami.service'

    if remove:
        subprocess.run(["/usr/bin/systemctl", "stop", "nuki-sesami"], check=False)
        subprocess.run(["/usr/bin/systemctl", "disable", "nuki-sesami"], check=False)
        subprocess.run(["/usr/bin/rm", "-vrf", systemd_fname], check=False)
        return

    sesami = shutil.which('nuki-sesami')
    if not sesami:
        logger.error("Failed to detect 'nuki-sesami' binary")
        sys.exit(1)

    pth = [x for x in sys.path if x.startswith('/home/')]
    env = 'PYTHONPATH=%s:$PYTHONPATH' % pth[0] if len(pth) else ''

    with open(systemd_fname, 'w+') as f:
        f.write(SYSTEMD_TEMPLATE % (env, sesami, device, host, username, password))
        logger.info("Created systemd file; '%s'", systemd_fname)

    try:
        subprocess.run(["/usr/bin/systemctl", "dAaemon-reload"], check=True)
        subprocess.run(["/usr/bin/systemctl", "enable", "nuki-sesami"], check=True)
        subprocess.run(["/usr/bin/systemctl", "start", "nuki-sesami"], check=True)
    except subprocess.CalledProcessError:
        logger.exception("Failed to install nuki-sesami systemd service")
        sys.exit(1)


def getlogger(name: str, path: str, level: int = logging.INFO) -> Logger:
    '''Returns a logger instance for the given name and path.

    The logger for will rotating log files with a maximum size of 1MB and
    a maximum of 10 log files.

    Parameters:
    * name: name of the logger, e.g. 'nuki-sesami'
    * path: complete path for storing the log files, e.g. '/var/log/nuki-sesami'
    * level: logging level, e.g; logging.DEBUG

    '''
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    handler = RotatingFileHandler(f'{os.path.join(path,name)}.log', maxBytes=1048576, backupCount=10)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    return logger


def is_virtual_env():
    '''Returns true when running in a virtual environment.'''
    return sys.prefix != sys.base_prefix


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
    root = sys.prefix if is_virtual_env() else '/'
    logpath = os.path.join(root, 'var/log/nuki-sesami-daemon')

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
        logger.error("Virtual environment detected, systemd is not supported")
        sys.exit(1)

    try:
        nuki_sesami_systemd(logger, args.device, args.host, args.username, args.password, args.remove)
    except KeyboardInterrupt:
        logger.info("Program terminated")
    except Exception:
        logger.exception("System daemon installation failed")


if __name__ == "__main__":
    main()
