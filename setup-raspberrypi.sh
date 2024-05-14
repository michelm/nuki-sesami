#!/bin/bash
#
# Example script to setup a Raspberry Pi with Nuki and Sesami
# This script is intended to be run on a fresh Raspberry Pi OS installation
# It will install required packages, setup mosquitto and create a virtual environment
# for nuki-sesami
# Change to your liking and/or preferences.
#
set -e -o pipefail

# install python packages
sudo apt update
sudo apt-get install -y python3-pip
sudo apt-get install -y python3-gpiozero
sudo apt-get install -y python3-paho-mqtt

# install bluetooth packages
sudo apt-get install -y bluez python3-bluez

# install mosquitto
sudo apt-get install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto.service

# create passwords file
sudo touch /etc/mosquitto/passwords
echo "nuki:secret1" | sudo tee -a /etc/mosquitto/passwords
echo "sesami:secret2" | sudo tee -a /etc/mosquitto/passwords
read -p "change passwords in /etc/mosquitto/passwords, press enter when done"
sudo mosquitto_passwd -U /etc/mosquitto/passwords

# configure mosquitto; disallow anonymous access, set path to passwords file
echo "listener 1883" | sudo tee -a /etc/mosquitto/mosquitto.conf
echo "allow_anonymous false" | sudo tee -a /etc/mosquitto/mosquitto.conf
echo "password_file /etc/mosquitto/passwords" | sudo tee -a /etc/mosquitto/mosquitto.conf
sudo systemctl restart mosquitto.service

# setup virtual enviuronment and install nuki-sesami
cd $(dirname "$0")
./setup-nuki-sesami.sh
