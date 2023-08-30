# Nuki Sesami

Open an electric door equipped with an _Nuki 3.0 Pro_ smart lock.

## Requirements

The following components are required when using this package:

- [Nuki 3.0 Pro smart lock](https://nuki.io/en/smart-lock-pro/) (or similar)
- **ERREKA Smart Evolution Pro** electric door controller (or similar)
- [Raspberry Pi](https://www.raspberrypi.org/) (or similar) with [Raspbian BullsEye](https://www.raspbian.org/) (or later) installed
- [Waveshare RPi relay board](https://www.waveshare.com/wiki/RPi_Relay_Board) (or similar)
- **mqtt** broker [mosquitto](https://mosquitto.org/), running on the same _Raspberry Pi_ board
- Pushbutton connected to the relay board

## Installation and setup

The package can be installed on the _Raspberry PI_ board as per usual:

```bash
pip3 install nuki-sesami
```

Installation and configuration of the **mosquitto** broker:
    
```bash
sudo apt update
sudo apt install mosquitto
sudo systemctl enable mosquitto
mosquitto_passwd /etc/mosquitto/passwd nuki <secret1>
mosquitto_passwd /etc/mosquitto/passwd sesami <secret2>
```

Ensure **mqtt** is enabled and running on the Nuki Smart Lock using the smartphone app.
Use the same credentials as above for the nuki user.

Activate **nuki-sesami** as systemd service:

```bash
nuki-sesami-setup --install-systemd
```

In the _BATS_ programming menu of the ERREKA door controller ensure the external switch for manual changing the operating mode
is activated:

- Function **FC01** == OFF, the door will be in _open/close_ mode when switch is in position **I**
- Function **FC07** == ON, the door will be in _open and hold_ mode when switch is in position **II**

Use wiring connection as depicted in the diagram below:

![nuki-sesami-wiring](nuki-raspi-door-erreka.png)

## Usage

TODO
