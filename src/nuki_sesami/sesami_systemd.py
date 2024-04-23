#!/bin/env python3

import os
import sys
import argparse
import subprocess
import shutil


SYSTEMD_TEMPLATE = f'''[Unit]
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


def nuki_sesami_systemd(device: str, host: str, username: str, password: str, remove: bool = False)  -> None:
    systemd_fname = f'/lib/systemd/system/nuki-sesami.service'

    if remove:
        subprocess.run(["systemctl", "stop", "nuki-sesami"])
        subprocess.run(["systemctl", "disable", "nuki-sesami"])
        subprocess.run(["rm", "-vrf", systemd_fname])
        return

    bin = shutil.which('nuki-sesami')
    if not bin:
        print(f"Failed to detect 'nuki-sesami' binary")
        sys.exit(1)

    try:
        env = 'PYTHONPATH=%s:$PYTHONPATH' % [x for x in sys.path if x.startswith('/home/')][0]
    except:
        env = ''

    with open(systemd_fname, 'w+') as f:
        f.write(SYSTEMD_TEMPLATE % (env, bin, device, host, username, password))
        print(f"Created systemd file; '{systemd_fname}'")

    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "nuki-sesami"], check=True)
        subprocess.run(["systemctl", "start", "nuki-sesami"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Something went wrong: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami-systemd',
        description='Setup nuki-sesami as systemd service',
        epilog='The way is shut. It was made by those who are Dead, and the Dead keep it, until the time comes. The way is shut.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument('device', help="nuki hexadecimal device id, e.g. 3807B7EC", type=str)
    parser.add_argument('-H', '--host', help="hostname or IP address of the mqtt broker, e.g. 'mqtt.local'", default='localhost', type=str)
    parser.add_argument('-U', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')
    parser.add_argument('-R', '--remove', help="Remove nuki-sesami systemd service", action='store_true')

    args = parser.parse_args()

    if args.verbose:
        print(f"device      : {args.device}")
        print(f"host        : {args.host}")
        print(f"username    : {args.username}")
        print(f"password    : ***")
        print(f"remove      : {args.remove}")

    if 'VIRTUAL_ENV' in os.environ:
        print("Virtual environment detected, systemd is not supported")
        sys.exit(1)

    try:
        nuki_sesami_systemd(args.device, args.host, args.username, args.password, args.remove)
    except KeyboardInterrupt:
        print("Program terminated")
    except Exception as e:
        print(f"Something went wrong: {e}")


if __name__ == "__main__":
    main()
