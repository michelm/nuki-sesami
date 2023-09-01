#!/bin/env python3

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
User=%s
Restart=always
RestartSec=1
ExecStart=%s %s -H %s -U %s -P %s
StandardError=journal
StandardOutput=journal
StandardInput=null

[Install]
WantedBy=multi-user.target
'''


def nuki_sesami_systemd(user: str, device: str, host: str, username: str, password: str, remove: bool = False)  -> None:
    if remove:
        subprocess.run(["systemctl", "stop", "nuki-sesami"])
        subprocess.run(["systemctl", "disable", "nuki-sesami"])
        subprocess.run(["rm", "-vrf", "/lib/systemd/system/nuki-sesami.service"])
        return

    bin = shutil.which('nuki-sesami')
    if not bin:
        print(f"Failed to detect 'nuki-sesami' binary")
        sys.exit(1)

    fname = f'/lib/systemd/system/nuki-sesami.service'
    with open(fname, 'w+') as f:
        f.write(SYSTEMD_TEMPLATE % (user, bin, device, host, username, password))
        print(f"Created systemd file; '{fname}'")

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

    parser.add_argument('user', help="user in the systemd service", type=str)
    parser.add_argument('device', help="nuki hexadecimal device id, e.g. 3807B7EC", type=str)
    parser.add_argument('-H', '--host', help="hostname or IP address of the mqtt broker, e.g. 'mqtt.local'", default='localhost', type=str)
    parser.add_argument('-U', '--username', help="mqtt authentication username", default=None, type=str)
    parser.add_argument('-P', '--password', help="mqtt authentication secret", default=None, type=str)
    parser.add_argument('-V', '--verbose', help="be verbose", action='store_true')
    parser.add_argument('-R', '--remove', help="Remove nuki-sesami systemd service", action='store_true')

    args = parser.parse_args()

    if args.verbose:
        print(f"user        : {args.user}")
        print(f"device      : {args.device}")
        print(f"host        : {args.host}")
        print(f"username    : {args.username}")
        print(f"password    : ***")
        print(f"remove      : {args.remove}")

    try:
        nuki_sesami_systemd(args.user, args.device, args.host, args.username, args.password, args.remove)
    except KeyboardInterrupt:
        print("Program terminated")
    except Exception as e:
        print(f"Something went wrong: {e}")


if __name__ == "__main__":
    main()
