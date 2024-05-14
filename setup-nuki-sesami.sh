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
username=${NUKI_SESAMI_USERNAME:-'sesami'}
password=${NUKI_SESAMI_PASSWORD}
pushbutton=${NUKI_SESAMI_PUSHBUTTON:-'openhold'}
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

echo "[INFO] configuring and starting nuki-sesami services"
nuki-sesami-admin setup \
    -d $device \
    -H $host \
    -m $macaddr \
    -U $username \
    -P $password \
    -B $pushbutton \
    --verbose

echo "[INFO] verify if systemd services are running"
sudo systemctl status nuki-sesami
sudo systemctl status nuki-sesami-bluez

echo "all done, services configured and running"
