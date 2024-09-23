#!/bin/bash
#
# Example script to setup Nuki Sesami in a virtual environment
# on a Raspberry Pi.
# Assumes mosquitto is already installed and configured and required
# system packages are installed.
# Change to your liking and/or preferences.
#
set -e -o pipefail

device=${NUKI_SESAMI_DEVICE:-'3807B7EC'}
host=${NUKI_SESAMI_HOST:-'raspi-door'}
macaddr=${NUKI_SESAMI_BLUE_MACADDR:-'B8:27:EB:B9:2A:F0'}
channel=${NUKI_SESAMI_BLUE_CHANNEL:-4}
backlog=${NUKI_SESAMI_BLUE_BACKLOG:-10}
username=${NUKI_SESAMI_USERNAME:-'sesami'}
password=${NUKI_SESAMI_PASSWORD}
pushbutton=${NUKI_SESAMI_PUSHBUTTON:-'openhold'}
opentime=${NUKI_SESAMI_DOOR_OPEN_TIME:-31}
unlatchtime=${NUKI_SESAMI_LOCK_UNLATCH_TIME:-16}
venv=${NUKI_SESAMI_VENV:-'nuki-sesami'}
package=${NUKI_SESAMI_PKG:-'nuki-sesami'}

if [ -d $HOME/$venv ] ; then
    echo "[INFO] removing virtual environment $HOME/$venv"
    rm -Ir $HOME/$venv
fi

echo "[INFO] creating virtual environment $HOME/$venv"
python3 -m venv --system-site-packages $HOME/$venv/

echo "[INFO] installing package $package in virtual environment $HOME/$venv"
source $HOME/$venv/bin/activate
pip3 install $package

echo "[INFO] removing old service log files"
sudo rm -f /var/log/nuki-sesami/nuki-sesami.log
sudo rm -f /var/log/nuki-sesami-bluez/nuki-sesami-bluez.log

echo "[INFO] configuring and starting nuki-sesami services"
nuki-sesami-admin setup \
    -d $device \
    -H $host \
    -m $macaddr \
    -b $channel \
    -n $backlog \
    -U $username \
    -P $password \
    -B $pushbutton \
    -O $opentime \
    -L $unlatchtime \
    --verbose
# force to the services to write to log files
sudo systemctl restart nuki-sesami
sudo systemctl restart nuki-sesami-bluez

echo "[INFO] verify if systemd services are running"
sudo systemctl status nuki-sesami
sudo systemctl status nuki-sesami-bluez

echo "all done, services configured and running"
