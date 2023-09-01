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
sudo nuki-sesami-systemd %USER <nuki-device-id> -H <mqtt-broker-hostname> -U sesami -P <secret2>
```

In the _BATS_ programming menu of the ERREKA door controller ensure the external switch for manual changing the operating mode
is activated:

- Function **FC01** == OFF, the door will be in _open/close_ mode when switch is in position **I**
- Function **FC07** == ON, the door will be in _open and hold_ mode when switch is in position **II**

Use wiring connection as depicted in the diagram below:

![nuki-sesami-wiring](nuki-raspi-door-erreka.png)

## Usage

Once the system has been setup as described above, the smartlock can be operated as per usual using the _Nuki_ smartphone app
and/or other _Nuki_ peripherals; like for instance the _Nuki Fob_.
As soon as the smartlock state changes from _unlatching_ to _unlatched_ the electric door will be opened by means
of the relay board using a short on/off puls on _Relay CH1_.

The relay board can also be operated manually using the pushbutton. This is useful when the door needs to be opened without 
the _Nuki_ app or _Nuki_ peripherals. When pressing pushbutton once the smartlock will be unlatched and the door will be opened.
If during the opening phase the pushbutton is pressed again, the door will be kept open (_openhold mode_) until the pushbutton
is pressed again.

Please note that when the system starts up, the door will be in _open/close_ mode; i.e. _Relay CH3_ will be active and _Relay CH2_
will be inactive. This is to ensure the door can be opened and closed as per usual. When the system is in in _openhold_ mode 
the relay states will be flipped; i.e. the _Relay CH3_ will be inactive and _Relay CH2_ will be active.
