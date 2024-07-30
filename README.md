# Nuki Sesami

Open (and hold) an electric door equipped with an _Nuki 3.0 Pro_ smart lock using a pushbutton and/or a smartphone using the _Nuki Sesami_ app.

## Overview

An electric door somehow needs to receive trigger signals for it to be _opened_, _closed_ or _held open_. The **Nuki Sesami** package can perform this logic for you when using an _ERREKA Smart Evolution Pro_ electric door controller in combination with an _Nuki 3.0 Pro_ smart lock.

![nuki-sesami-wiring](https://raw.githubusercontent.com/michelm/nuki-sesami/master/nuki-sesami-overview.png)

The door will be _opened_ by the _Nuki Sesami_ service when the smart lock is _unlatched_ using the _Nuki Smartlock_ app. After a brief moment the door will close again.
The door can also be  _opened_ **and** _held open_ by pressing a pushbutton connected to the _Raspberry Pi_ board on which the _Nuki Sesami_ service is running. When pressing this pushbutton again the door will be _closed_ again.
Finally the door can be _opened_, _held open_ or _closed_ using the [_Nuki Sesami_ Smartphone App](https://github.com/michelm/nuki-sesami-app). Communication between the _Nuki Sesami_ service and the _Nuki 3.0_ smart lock is achieved using the _mqtt_ protocol; e.g. by running a _Mosquitto_ (**mqtt**) broker on the _Raspberry Pi_ board. Communication between the _Nuki Sesami_ service and the _Nuki Sesami_ smartphone app can be achieved using the _mqtt_ protocol or using _bluetooth_.

## Requirements

The following components are required when using this package:

- [Nuki 3.0 Pro smart lock](https://nuki.io/en/smart-lock-pro/) (or similar)
- **ERREKA Smart Evolution Pro** electric door controller (or similar)
- [Raspberry Pi](https://www.raspberrypi.org/) (or similar) with [Raspbian BullsEye](https://www.raspbian.org/) (or later) installed
- [Waveshare RPi relay board](https://www.waveshare.com/wiki/RPi_Relay_Board) (or similar)
- **mqtt** broker [mosquitto](https://mosquitto.org/), running on the same _Raspberry Pi_ board
- Pushbutton connected to the relay board
- Android (**v11+**) smartphone with the _Nuki Sesami_ app installed

## Installation and setup

The package can be installed on the _Raspberry PI_ board using following commands:

```bash
sudo apt update
sudo apt-get install -y python3-pip python3-gpiozero bluez pi-bluetooth
python3 -m venv --system-site-packages $HOME/nuki-sesami
source $HOME/nuki-sesami/bin/activate
pip3 install nuki-sesami
```

In order for **nuki-sesami** to be able to communicate with the _Nuki_ smart lock, a _Mosquitto_ broker must be running and configured. The bash script below can be used to install and configure the _Mosquitto_ broker (on the same _Raspberry Pi_ board):

```bash
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
echo "android:secret3" | sudo tee -a /etc/mosquitto/passwords
read -p "change passwords in /etc/mosquitto/passwords, press enter when done"
sudo mosquitto_passwd -U /etc/mosquitto/passwords

echo "[INFO] configure mosquitto; disallow anonymous access, set path to passwords file"
echo "listener 1883" | sudo tee -a /etc/mosquitto/mosquitto.conf
echo "allow_anonymous false" | sudo tee -a /etc/mosquitto/mosquitto.conf
echo "password_file /etc/mosquitto/passwords" | sudo tee -a /etc/mosquitto/mosquitto.conf
sudo systemctl restart mosquitto.service

echo "[INFO] verify if systemd services are running"
sudo systemctl status mosquitto.service
```

Once the _Mosquitto_ broker is running, the _Nuki_ smart lock can be configured to communicate with the _Mosquitto_ **mqtt** broker using the _Nuki Sesami_ app running on your smartphone:

- Go to the setting of your smart lock, by pressing _Settings_ in the lower right of the screen
- Press _Features & Configuration_ and select the _MQTT_ feature
- Enable the _MQTT_ feature and enter the following settings:
  - **Host name**: hostname of the _Raspberry Pi_ board running the _Mosquitto_ broker
  - **User name**: nuki
  - **Password**: _nuki-password_
  - **Auto discovery**: on
  - **Allow locking**: on

Verify the _Nuki_ smart lock is able to communicate with the _Mosquitto_ broker by using the following command on the _Raspberry Pi_ board:

```bash
mosquitto_sub -h <mqtt-broker-hostname> -p 1883 -u sesami -P <sesami-password> -t nuki/DEVID/state
```

Where **DEVID** is the hexadecimal device ID; e.g. **3807B7EC**, of the _Nuki_ smart lock. The device ID can be found in the _Nuki_ app under _Settings_ > _Features & Configuration_ > _General_.

Next step is to configure and start the _Nuki Sesami_ systemd services, as presented in the example below:

```bash
device=${NUKI_SESAMI_DEVICE:-'3807B7EC'}
host=${NUKI_SESAMI_HOST:-'raspi-door'}
macaddr=${NUKI_SESAMI_BLUE_MACADDR:-'B8:27:EB:B9:2A:F0'}
channel=${NUKI_SESAMI_BLUE_CHANNEL:-4}
backlog=${NUKI_SESAMI_BLUE_BACKLOG:-10}
username=${NUKI_SESAMI_USERNAME:-'sesami'}
password=${NUKI_SESAMI_PASSWORD}
pushbutton=${NUKI_SESAMI_PUSHBUTTON:-'openhold'}

nuki-sesami-admin setup \
    -d $device \
    -H $host \
    -m $macaddr \
    -b $channel \
    -n $backlog \
    -U $username \
    -P $password \
    -B $pushbutton \
    --verbose

sudo systemctl restart nuki-sesami
sudo systemctl restart nuki-sesami-bluez
```

Next pair all smartphones using the _Nuki Sesami_ app with the _Raspberry Pi_ board running the _Nuki Sesami_ services:

- Lookup the bluetooth address and name of your smartphone
- Ensure bluetooth is running on the _Raspberry pi_ board:

  - `sudo systemctl status bluetooth.service`

- Pair the smartphone with the _Raspberry Pi_ board:

  - `sudo bluetoothctl`
  - `power on`
  - `scan on`
  - ensure the smartphone's bluetooth address is listed
  - `scan off`
  - `pair <bluetooth-address>`
  - `trust <bluetooth-address>`

Repeat steps above for all smartphones that need to be paired with the _Raspberry Pi_ board.

Final step is to configure the _ERREKA Smart Evolution Pro_ electric door controller to operate the electric door as per the _Nuki_ smart lock state.
In the _BATS_ programming menu of the ERREKA door controller ensure the external switch for manual changing the operating mode is activated:

- Function **FC01** == OFF, the door will be in _open/close_ mode when switch is in position **I**
- Function **FC07** == ON, the door will be in _open and hold_ mode when switch is in position **II**

Use wiring connection as depicted in the diagram below:

![nuki-sesami-wiring](https://raw.githubusercontent.com/michelm/nuki-sesami/master/nuki-raspi-door-erreka.png)

## Door controller operation

Once the system has been setup as described above, the smartlock can be operated as per usual using the _Nuki_ smartphone app
and/or other _Nuki_ peripherals; like for instance the _Nuki Fob_.
As soon as the smartlock state changes from _unlatching_ to _unlatched_ the electric door will be opened by means
of the relay board using a short on/off puls on _Relay CH1_.

The relay board can also be operated manually using a pushbutton. This is useful when the door needs to be opened without
the _Nuki_ app or _Nuki_ peripherals and/or change the door operating mode.
The pushbutton logic can be as follows:

- **pushbutton-openhold** When pressing the pushbutton once the smartlock will be unlatched and the door will be opened
and held open (_openhold mode_) until the pushbutton is pressed again (**default** logic).

- **pushbutton-open** When pressing the pushbutton once the smartlock will be unlatched and the door will be opened. After a
few seconds the door will automaticaly be closed again.

- **pushbutton-toggle** When pressing the pushbutton once the smartlock will be unlatched and the door will be opened. If during
the opening phase the pushbutton is pressed again, the door will be kept open (_openhold mode_) until the pushbutton is pressed again.
Otherwise the door will be closed again after a few seconds.

Please note that when the system starts up, the door will be in _open/close_ mode; i.e. _Relay CH3_ will be active and _Relay CH2_
will be inactive. This is to ensure the door can be opened and closed as per usual. When the system is in in _openhold_ mode the relay states will be flipped; i.e. the _Relay CH3_ will be inactive and _Relay CH2_ will be active.
