#
# Use gpiozero mock factory when testing:
#   export GPIOZERO_PIN_FACTORY=mock
#
# See https://gpiozero.readthedocs.io/en/stable/api_output.html#gpiozero.pins.mock.MockFactory
# for more information.

import argparse
import asyncio
import importlib.metadata
import logging
import os
import sys
import datetime
from logging import Logger

import aiomqtt
from gpiozero import Button, DigitalOutputDevice

from nuki_sesami.config import SesamiConfig, get_config
from nuki_sesami.lock import NukiDoorsensorState, NukiLockAction, NukiLockState
from nuki_sesami.state import DoorMode, DoorRequestState, DoorState, PushbuttonLogic
from nuki_sesami.util import get_config_path, get_prefix, getlogger

PUSHBUTTON_TRIGGER_UUID = '09c69301-d115-4c3d-b614-b32bac1cf120'


async def mqtt_publish_nuki_lock_action(client: aiomqtt.Client, device: str, logger: Logger, action: NukiLockAction):
    topic = f"nuki/{device}/lockAction"
    logger.info('[mqtt] publish %s=%s:%i (retain)', topic, action.name, action.value)
    await client.publish(topic, action.value, retain=True)


async def mqtt_publish_sesami_version(client: aiomqtt.Client, device: str, logger: Logger, version: str):
    topic = f"sesami/{device}/version"
    logger.info('[mqtt] publish %s=%s (retain)', topic, version)
    await client.publish(topic, version, retain=True)


async def mqtt_publish_sesami_state(client: aiomqtt.Client, device: str, logger: Logger, state: DoorState):
    topic = f"sesami/{device}/state"
    logger.info('[mqtt] publish %s=%s:%i (retain)', topic, state.name, state.value)
    await client.publish(topic, state.value, retain=True)


async def mqtt_publish_sesami_mode(client: aiomqtt.Client, device: str, logger: Logger, state: DoorMode):
    topic = f"sesami/{device}/mode"
    logger.info('[mqtt] publish %s=%s:%i (retain)', topic, state.name, state.value)
    await client.publish(topic, state.value, retain=True)


async def mqtt_publish_sesami_relay_state(client: aiomqtt.Client, device: str, name: str,
                                          logger: Logger, state: int, retain=True):
    topic = f"sesami/{device}/relay/{name}"
    logger.info('[mqtt] publish %s=%i (retain=%s)', topic, state, retain)
    await client.publish(topic, state, retain=retain)


async def mqtt_publish_sesami_relay_opendoor_blink(client: aiomqtt.Client, device: str, logger: Logger):
    await mqtt_publish_sesami_relay_state(client, device, 'opendoor', logger, 1, retain=True)
    await asyncio.sleep(1)
    await mqtt_publish_sesami_relay_state(client, device, 'opendoor', logger, 0, retain=True)


async def check_door_state(door, door_open_time, lock_unlatch_time, check_interval=3):
    while True:
        await asyncio.sleep(check_interval)
        dt = datetime.datetime.now() - door.state_changed_time
        if door.state == DoorState.opened:
            dt_open = datetime.timedelta(seconds=door_open_time)
            if dt > dt_open:
                door.state = DoorState.closed
        elif door.state == DoorState.openhold:
            dt_unlatched = datetime.timedelta(seconds=lock_unlatch_time)
            if dt > dt_unlatched and not door.gpio_openhold_set:
                door.state = DoorState.closed


class Relay(DigitalOutputDevice):
    def __init__(self, pin, active_high):
        super().__init__(pin, active_high=active_high)


class PushButton(Button):
    def __init__(self, pin, userdata, *args, **kwargs):
        super().__init__(pin, *args, **kwargs)
        self.userdata = userdata


def pushbutton_held(button):
    door = button.userdata
    door.logger.info("(input) door (open/hold/close) push button %s is held", button.pin)


def pushbutton_pressed(button):
    door = button.userdata
    door.logger.info("(input) door (open/hold/close) push button %s is pressed", button.pin)
    door.pushbutton_triggered(PUSHBUTTON_TRIGGER_UUID)
    door.on_pushbutton_pressed()


def pushbutton_released(button):
    door = button.userdata
    door.logger.info("(input) door (open/hold/close) push button %s is released", button.pin)


class ElectricDoor:
    '''Opens an electric door based on the Nuki smart lock state

    Subscribes as client to MQTT door status topic from 'Nuki 3.0 pro' smart lock. When the lock has been opened
    it will activate a relay, e.g. using the 'RPi Relay Board', triggering the electric door to open.
    '''
    def __init__(self, logger: Logger, config: SesamiConfig, version: str):
        self._logger = logger
        self._version = version
        self._nuki_device = config.nuki_device
        self._nuki_state = NukiLockState.undefined
        self._nuki_doorsensor = NukiDoorsensorState.unknown
        self._pushbutton = PushButton(config.gpio_pushbutton, self, bounce_time=1.0)
        self._pushbutton.when_pressed = pushbutton_pressed
        self._pushbutton_trigger = None
        self._opendoor = Relay(config.gpio_opendoor, False) # uses normally open relay (NO)
        self._openhold_mode = Relay(config.gpio_openhold_mode, False) # uses normally open relay (NO)
        self._openclose_mode = Relay(config.gpio_openclose_mode, False) # uses normally open relay (NO)
        self._state = DoorState.closed
        self._state_changed = datetime.datetime.now()
        self._door_open_time = config.door_open_time
        self._lock_unlatch_time = config.lock_unlatch_time
        self._clients = [] # list of connected bluetooth clients
        self._background_tasks = set()

    def run_coroutine(self, coroutine):
        '''Wraps the coroutine into a task and schedules its execution

        The task will be added to the set of background tasks.
        This creates a strong reference.

        To prevent keeping references to finished tasks forever,
        the task removes its own reference from the set of background tasks
        after completion.

        When called from a thread running outside of the event loop context
        it is scheduled using asyncio.run_coroutine_threadsafe
        '''
        try:
            _ = asyncio.get_running_loop()
            task = asyncio.create_task(coroutine)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    def activate(self, client: aiomqtt.Client, loop: asyncio.AbstractEventLoop):
        '''Activates the electric door logic

        Initializes GPIO to pins to default state, publishes initial (relay) states
        and modes on MQTT.
        '''
        self._mqtt = client
        self._loop = loop
        self.logger.info("(relay) opendoor(0), openhold(0), openclose(1)")
        self._opendoor.off()
        self._openhold_mode.off()
        self._openclose_mode.on()
        self.run_coroutine(check_door_state(self, self._door_open_time, self._lock_unlatch_time))

        for name, state in [('opendoor', 0), ('openhold', 0), ('openclose', 1)]:
            self.run_coroutine(mqtt_publish_sesami_relay_state(
                self._mqtt, self.nuki_device, name, self.logger, state, retain=True))
            
        self.run_coroutine(mqtt_publish_sesami_version(
            self._mqtt, self.nuki_device, self.logger, self.version))

        self.run_coroutine(mqtt_publish_sesami_state(
            self._mqtt, self.nuki_device, self.logger, self.state))

        self.run_coroutine(mqtt_publish_sesami_mode(
            self._mqtt, self.nuki_device, self.logger, self.mode))

    @property
    def classname(self) -> str:
        return type(self).__name__

    @property
    def logger(self) -> Logger:
        return self._logger
    
    @property
    def version(self) -> str:
        return self._version

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    @property
    def nuki_device(self) -> str:
        return self._nuki_device

    @property
    def lock(self) -> NukiLockState:
        return self._nuki_state

    @lock.setter
    def lock(self, state: NukiLockState):
        self._nuki_state = state

    @property
    def sensor(self) -> NukiDoorsensorState:
        return self._nuki_doorsensor

    @sensor.setter
    def sensor(self, state: NukiDoorsensorState):
        self._nuki_doorsensor = state

    @property
    def state(self) -> DoorState:
        return self._state

    @state.setter
    def state(self, state: DoorState):
        if state == self._state:
            return
        self.logger.info("(state) %s -> %s", self._state.name, state.name)
        self._state = state
        self._state_changed = datetime.datetime.now()
        self.run_coroutine(mqtt_publish_sesami_state(
            self._mqtt, self.nuki_device, self.logger, state))
        self.run_coroutine(mqtt_publish_sesami_mode(
            self._mqtt, self.nuki_device, self.logger, self.mode))

    @property
    def state_changed_time(self) -> datetime.datetime:
        return self._state_changed

    @property
    def mode(self) -> DoorMode:
        return DoorMode.openhold if self._state == DoorState.openhold else DoorMode.openclose

    @property
    def gpio_openhold_set(self) -> bool:
        return self._openhold_mode.value != 0 
    
    @property
    def gpio_openclose_set(self) -> bool:
        return self._openclose_mode.value != 0 

    def pushbutton_triggered(self, uuid: str):
        '''Set by the pushbutton callback function, ensuring the pushbutton has been triggered

        TODO: temporary solution, use until bug has been found triggering the pushbutton
        function.
        '''
        self._pushbutton_trigger = uuid

    def lock_action(self, action: NukiLockAction):
        self.logger.info("(lock) request action=%s:%i", action.name, int(action))
        self.run_coroutine(mqtt_publish_nuki_lock_action(
            self._mqtt, self.nuki_device, self.logger, action))

    def unlatch(self):
        if self.lock in [NukiLockState.unlatching]:
            return
        self.logger.info("(unlatch) state=%s:%i, lock=%s:%i", self.state.name, self.state, self.lock.name, self.lock)
        self.lock_action(NukiLockAction.unlatch)

    def unlock(self):
        self.logger.info("(unlock) state=%s:%i, lock=%s:%i", self.state.name, self.state, self.lock.name, self.lock)
        self.lock_action(NukiLockAction.unlock)

    def open(self):
        self.logger.info("(open) state=%s:%i, lock=%s:%i", self.state.name, self.state, self.lock.name, self.lock)
        self.logger.info("(relay) opendoor(blink 1[s])")
        self._opendoor.blink(on_time=1, off_time=1, n=1, background=True)
        self.run_coroutine(mqtt_publish_sesami_relay_opendoor_blink(
            self._mqtt, self.nuki_device, self.logger))

    def openhold(self):
        self.logger.info("(openhold) state=%s:%i, lock=%s:%i", self.state.name, self.state, self.lock.name, self.lock)
        self.logger.info("(relay) openhold(1), openclose(0)")
        self._openhold_mode.on()
        self._openclose_mode.off()
        for name, state in [('opendoor', 0), ('openhold', 1), ('openclose', 0)]:
            self.run_coroutine(mqtt_publish_sesami_relay_state(
                self._mqtt, self.nuki_device, name, self.logger, state, retain=True))
        self.run_coroutine(mqtt_publish_sesami_mode(
            self._mqtt, self.nuki_device, self.logger, DoorMode.openhold))

    def close(self):
        self.logger.info("(close) state=%s:%i, lock=%s:%i", self.state.name, self.state, self.lock.name, self.lock)
        if self.lock in [NukiLockState.locked, NukiLockState.locking]:
            self.unlock()
        self.logger.info("(relay) openhold(0), openclose(1)")
        self._openhold_mode.off()
        self._openclose_mode.on()
        for name, state in [('opendoor', 0), ('openhold', 0), ('openclose', 1)]:
            self.run_coroutine(mqtt_publish_sesami_relay_state(
                self._mqtt, self.nuki_device, name, self.logger, state, retain=True))
        self.run_coroutine(mqtt_publish_sesami_mode(
            self._mqtt, self.nuki_device, self.logger, DoorMode.openclose))

    def on_lock_state(self, lock: NukiLockState):
        self.logger.info("(lock_state) state=%s:%i, lock=%s:%i -> %s:%i",
                         self.state.name, self.state, self.lock.name, self.lock, lock.name, lock)
        current = self.lock
        self.lock = lock
        if current == NukiLockState.unlatching and lock == NukiLockState.unlatched:
            if self.state == DoorState.openhold:
                self.openhold()
            else:
                self.open()

    def on_doorsensor_state(self, sensor: NukiDoorsensorState):
        self.logger.info("(doorsensor_state) state=%s:%i, sensor=%s:%i -> %s:%i",
                         self.state.name, self.state, self.sensor.name, self.sensor, sensor.name, sensor)
        self.sensor = sensor
        if sensor == NukiDoorsensorState.door_closed and self.state == DoorState.opened:
            self.state = DoorState.closed
        if sensor == NukiDoorsensorState.door_opened and self.state == DoorState.closed:
            self.state = DoorState.opened

    def on_door_request(self, request: DoorRequestState):
        '''Process a requested door state received from the MQTT broker.

        The Door request state is used to open/close the door and/or hold the door
        open based on the current door state and mode.

        Request processing logic:
        - open
            * if door is closed then open the door
            * if door is in openhold mode then ignore the request
        - close:
            * if door is in openhold mode then close the door
        - openhold:
            * if door is not open then open it and keep it open
            * ignore request if already in openhold mode
        - none:
            * ignore request

        Parameters:
        * request: the requested door state
        '''
        self.logger.info("(door_request) state=%s:%i, lock=%s:%i, request=%s:%i",
                         self.state.name, self.state, self.lock.name, self.lock, request.name, request)
        if request == DoorRequestState.none:
            return
        if request == DoorRequestState.open:
            if self.state == DoorState.closed:
                self.state = DoorState.opened
                self.unlatch() # open the door once lock is unlatched
        elif request == DoorRequestState.close:
            if self.state == DoorState.openhold:
                self.state = DoorState.opened # change to normal open/close mode
                self.close()
        elif request == DoorRequestState.openhold and self.state != DoorState.openhold:
            self.state = DoorState.openhold
            self.unlatch() # open the door (and hold it open) once lock is unlatched

    def on_pushbutton_pressed(self):
        if self._pushbutton_trigger != PUSHBUTTON_TRIGGER_UUID:
            self.logger.warning("(%s.pushbutton_pressed) but not triggered!", self.classname)
            return

        self._pushbutton_trigger = None
        self.logger.info("(%s.pushbutton_pressed)", self.classname)


class ElectricDoorPushbuttonOpenHold(ElectricDoor):
    '''Electric door with pushbutton 'open and hold' logic

    When pressing the pushbutton the door will be opened and held open until the pushbutton is pressed again.
    '''
    def __init__(self, logger: logging.Logger, config: SesamiConfig, version: str):
        super().__init__(logger, config, version)

    def _next_door_state(self, state: DoorState) -> DoorState:
        return DoorState.openhold if state == DoorState.closed else DoorState.closed

    def on_pushbutton_pressed(self):
        if self._pushbutton_trigger != PUSHBUTTON_TRIGGER_UUID:
            self.logger.warning("(%s.pushbutton_pressed) but not triggered!", self.classname)
            return

        self._pushbutton_trigger = None
        self.state = self._next_door_state(self.state)
        self.logger.info("(%s.pushbutton_pressed) state=%s:%i, lock=%s:%i",
                         self.classname, self.state.name, self.state, self.lock.name, self.lock)
        if self.state == DoorState.openhold:
            self.unlatch() # open the door once lock is unlatched
        else:
            self.close()


class ElectricDoorPushbuttonOpen(ElectricDoor):
    '''Electric door with pushbutton open logic

    When pressing the pushbutton the door will be opened for a few seconds after which it will be closed again.
    '''
    def __init__(self, logger: logging.Logger, config: SesamiConfig, version: str):
        super().__init__(logger, config, version)

    def on_pushbutton_pressed(self):
        if self._pushbutton_trigger != PUSHBUTTON_TRIGGER_UUID:
            self.logger.warning("(%s.pushbutton_pressed) but not triggered!", self.classname)
            return

        self._pushbutton_trigger = None
        self.state = DoorState.opened
        self.logger.info("(%s.pushbutton_pressed) state=%s:%i, lock=%s:%i",
                         self.classname, self.state.name, self.state, self.lock.name, self.lock)
        self.unlatch() # open the door once lock is unlatched


class ElectricDoorPushbuttonToggle(ElectricDoor):
    '''Electric door with pushbutton toggle logic

    When pressing the pushbutton the door will open, if during the smart lock unlatching
    phase of the pushbutton is pressed again the door will be held open until the pushbutton
    is pressed again.
    '''
    def __init__(self, logger: logging.Logger, config: SesamiConfig, version: str):
        super().__init__(logger, config, version)

    def _next_door_state(self, state: DoorState) -> DoorState:
        return DoorState((state + 1) % len(DoorState))

    def on_pushbutton_pressed(self):
        if self._pushbutton_trigger != PUSHBUTTON_TRIGGER_UUID:
            self.logger.warning("(%s.pushbutton_pressed) but not triggered!", self.classname)
            return

        self._pushbutton_trigger = None
        self.state = self._next_door_state(self.state)
        self.logger.info("(%s.pushbutton_pressed) state=%s:%i, lock=%s:%i",
                         self.classname, self.state.name, self.state, self.lock.name, self.lock)
        if self.state == DoorState.closed:
            self.unlatch() # open the door once lock is unlatched
        elif self.state == DoorState.opened:
            self.close()
        elif self.state == DoorState.openhold:
            pass # no action here


async def mqtt_receiver(client: aiomqtt.Client, door: ElectricDoor):
    async for msg in client.messages:
        payload = msg.payload.decode()
        topic = str(msg.topic)
        door.logger.info('[mqtt] receive %s=%s', topic, payload)
        if topic == f"nuki/{door.nuki_device}/state":
            door.on_lock_state(NukiLockState(int(payload)))
        elif topic == f"nuki/{door.nuki_device}/doorsensorState":
            door.on_doorsensor_state(NukiDoorsensorState(int(payload)))
        elif topic == f"sesami/{door.nuki_device}/request/state":
            door.on_door_request(DoorRequestState(int(payload)))


async def activate(logger: Logger, config: SesamiConfig, version: str):
    if config.pushbutton == PushbuttonLogic.open:
        door = ElectricDoorPushbuttonOpen(logger, config, version)
    elif config.pushbutton == PushbuttonLogic.toggle:
        door = ElectricDoorPushbuttonToggle(logger, config, version)
    else:
        door = ElectricDoorPushbuttonOpenHold(logger, config, version)

    async with aiomqtt.Client(config.mqtt_host, port=config.mqtt_port,
            username=config.mqtt_username, password=config.mqtt_password) as client:
        loop = asyncio.get_running_loop()
        door.activate(client, loop)
        await client.subscribe(f"nuki/{door.nuki_device}/state")
        await client.subscribe(f"nuki/{door.nuki_device}/doorsensorState")
        await client.subscribe(f"sesami/{door.nuki_device}/request/state")
        await mqtt_receiver(client, door)


def main():
    parser = argparse.ArgumentParser(
        prog='nuki-sesami',
        description='Open and close an electric door equipped with a Nuki 3.0 pro smart lock',
        epilog='Belrog: you shall not pass!',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument('-p', '--prefix',
                        help="runtime system root; e.g. '~/.local' or '/'",
                        type=str, default=None)
    parser.add_argument('-c', '--cpath',
                        help="configuration path; e.g. '/etc/nuki-sesami' or '~/.config/nuki-sesami'",
                        type=str, default=None)
    parser.add_argument('-V', '--verbose',
                        help="be verbose", action='store_true')
    parser.add_argument('-v', '--version',
                        help="print version and exit", action='store_true')

    args = parser.parse_args()
    version = importlib.metadata.version('nuki-sesami')
    if args.version:
        print(version)
        sys.exit(0)

    prefix = args.prefix or get_prefix()
    cpath = args.cpath or get_config_path()
    logpath = os.path.join(prefix, 'var/log/nuki-sesami')

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger('nuki-sesami', logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    config = get_config(cpath)

    logger.info("version        : %s", version)
    logger.info("prefix         : %s", prefix)
    logger.info("config-path    : %s", cpath)
    logger.info("pushbutton     : %s", config.pushbutton.name)
    logger.info("nuki.device    : %s", config.nuki_device)
    logger.info("mqtt.host      : %s", config.mqtt_host)
    logger.info("mqtt.port      : %i", config.mqtt_port)
    logger.info("mqtt.username  : %s", config.mqtt_username)
    logger.info("mqtt.password  : %s", '***')
    logger.info("gpio.pushbutton: %s", config.gpio_pushbutton)
    logger.info("gpio.opendoor  : %s", config.gpio_opendoor)
    logger.info("gpio.openhold  : %s", config.gpio_openhold_mode)
    logger.info("gpio.openclose : %s", config.gpio_openclose_mode)

    try:
        asyncio.run(activate(logger, config, version))
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
