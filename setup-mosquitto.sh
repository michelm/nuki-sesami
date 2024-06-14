#!/bin/bash
#
# Example script to setup a Mosquitto broker on a fresh RaspberryPi.
#
set -e -o pipefail

echo "[INFO] install packages and enable systemd service"
sudo apt update
sudo apt-get install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto.service

echo "[INFO] create passwords file"
sudo touch /etc/mosquitto/passwords
echo "nuki:secret1" | sudo tee -a /etc/mosquitto/passwords
echo "sesami:secret2" | sudo tee -a /etc/mosquitto/passwords
read -p "change passwords in /etc/mosquitto/passwords, press enter when done"
sudo mosquitto_passwd -U /etc/mosquitto/passwords

echo "[INFO] configure mosquitto; disallow anonymous access, set path to passwords file"
echo "listener 1883" | sudo tee -a /etc/mosquitto/mosquitto.conf
echo "allow_anonymous false" | sudo tee -a /etc/mosquitto/mosquitto.conf
echo "password_file /etc/mosquitto/passwords" | sudo tee -a /etc/mosquitto/mosquitto.conf
sudo systemctl restart mosquitto.service

echo "[INFO] verify if systemd services are running"
sudo systemctl status mosquitto.service
