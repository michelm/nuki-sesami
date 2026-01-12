from __future__ import annotations

import asyncio
import datetime
import logging
from logging import Logger
from typing import TYPE_CHECKING

import aiomqtt
from gpiozero import Button, DigitalOutputDevice

from nuki_sesami.config import SesamiConfig
from nuki_sesami.lock import NukiDoorsensorState, NukiLockAction, NukiLockActionEvent, NukiLockState, NukiLockTrigger
from nuki_sesami.state import DoorMode, DoorOpenTrigger, DoorState

if TYPE_CHECKING:
    from nuki_sesami.logic import PushbuttonStrategy


async def mqtt_publish_nuki_lock_action(
    client: aiomqtt.Client, device: str, logger: Logger, action: NukiLockAction
) -> None:
    topic = f"nuki/{device}/lockAction"
    logger.info("[mqtt] publish %s=%s:%i", topic, action.name, action.value)
    await client.publish(topic, action.value, retain=False)


async def mqtt_publish_sesami_version(client: aiomqtt.Client, device: str, logger: Logger, version: str) -> None:
    topic = f"sesami/{device}/version"
    logger.info("[mqtt] publish %s=%s (retain)", topic, version)
    await client.publish(topic, version, retain=True)


async def mqtt_publish_sesami_state(client: aiomqtt.Client, device: str, logger: Logger, state: DoorState) -> None:
    topic = f"sesami/{device}/state"
    logger.info("[mqtt] publish %s=%s:%i (retain)", topic, state.name, state.value)
    await client.publish(topic, state.value, retain=True)


async def mqtt_publish_sesami_mode(client: aiomqtt.Client, device: str, logger: Logger, state: DoorMode) -> None:
    topic = f"sesami/{device}/mode"
    logger.info("[mqtt] publish %s=%s:%i (retain)", topic, state.name, state.value)
    await client.publish(topic, state.value, retain=True)


async def mqtt_publish_sesami_relay_state(
    client: aiomqtt.Client, device: str, name: str, logger: Logger, state: int, retain=True
) -> None:
    topic = f"sesami/{device}/relay/{name}"
    logger.info("[mqtt] publish %s=%i%s", topic, state, " (retain)" if retain else "")
    await client.publish(topic, state, retain=retain)


async def mqtt_publish_sesami_relay_opendoor_blink(client: aiomqtt.Client, device: str, logger: Logger) -> None:
    await mqtt_publish_sesami_relay_state(client, device, "opendoor", logger, 1)
    await asyncio.sleep(1)
    await mqtt_publish_sesami_relay_state(client, device, "opendoor", logger, 0)


async def timed_door_closed(door: ElectricDoor, open_time: float, close_time: float, check_interval: float = 3.0) -> None:
    """Verifies and corrects the (logical) door state to closed when needed."""
    while True:
        await asyncio.sleep(check_interval)
        dt = datetime.datetime.now(tz=datetime.UTC) - door.state_changed_time
        if door.state == DoorState.opened:
            dt_open = datetime.timedelta(seconds=open_time)
            if dt > dt_open:
                door.state = DoorState.closed
        elif door.state == DoorState.openhold:
            dt_unlatched = datetime.timedelta(seconds=close_time)
            if dt > dt_unlatched and not door.gpio_openhold_set:
                door.state = DoorState.closed


async def timed_lock_unlatched(door: ElectricDoor, unlatch_time: float = 4.0) -> None:
    """Verifies the lock unlatches when instructed."""
    await asyncio.sleep(unlatch_time)
    if door.lock != NukiLockState.unlatching:
        return
    door.on_lock_unlatched(DoorOpenTrigger.unlatch_timeout)


class Relay(DigitalOutputDevice):
    def __init__(self, pin, active_high):
        super().__init__(pin, active_high=active_high)


class PushButton(Button):
    def __init__(self, pin, userdata, *args, **kwargs):
        super().__init__(pin, *args, **kwargs)
        self.userdata = userdata


def pushbutton_pressed(button: PushButton) -> None:
    door = button.userdata
    door.logger.info("(input) door (open/hold/close) push button %s is pressed", button.pin)
    door.on_pushbutton_pressed()


class ElectricDoor:
    """Opens an electric door based on the Nuki smart lock state."""

    def __init__(self, logger: Logger, config: SesamiConfig, version: str, strategy: PushbuttonStrategy):
        self._logger = logger
        self._version = version
        self._nuki_device = config.nuki_device
        self._nuki_state = NukiLockState.undefined
        self._nuki_doorsensor = NukiDoorsensorState.unknown
        self._nuki_action = None
        self._nuki_action_event = None
        self._pushbutton = PushButton(config.gpio_pushbutton, self, bounce_time=1.0)
        self._pushbutton.when_pressed = pushbutton_pressed
        self._opendoor = Relay(config.gpio_opendoor, False)
        self._openhold_mode = Relay(config.gpio_openhold_mode, False)
        self._openclose_mode = Relay(config.gpio_openclose_mode, False)
        self._state = DoorState.closed
        self._state_changed = datetime.datetime.now(tz=datetime.UTC)
        self._door_opened = False
        self._door_open_time = config.door_open_time
        self._door_close_time = config.door_close_time
        self._lock_unlatch_time = config.lock_unlatch_time
        self._background_tasks = set()
        self._strategy = strategy
        self._mqtt = None
        self._loop = None

    def run_coroutine(self, coroutine) -> None:
        """Wraps the coroutine into a task and schedules its execution."""
        try:
            _ = asyncio.get_running_loop()
            task = asyncio.create_task(coroutine)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            if self._loop:
                asyncio.run_coroutine_threadsafe(coroutine, self._loop)

    def activate(self, client: aiomqtt.Client, loop: asyncio.AbstractEventLoop) -> None:
        """Activates the electric door logic."""
        self._mqtt = client
        self._loop = loop
        self.logger.info("(relay) opendoor(0), openhold(0), openclose(1)")
        self._opendoor.off()
        self._openhold_mode.off()
        self._openclose_mode.on()
        self.run_coroutine(timed_door_closed(self, self._door_open_time, self._door_close_time))

        for name, state in [("opendoor", 0), ("openhold", 0), ("openclose", 1)]:
            self.run_coroutine(mqtt_publish_sesami_relay_state(self._mqtt, self.nuki_device, name, self.logger, state))

        self.run_coroutine(mqtt_publish_sesami_version(self._mqtt, self.nuki_device, self.logger, self.version))
        self.run_coroutine(mqtt_publish_sesami_state(self._mqtt, self.nuki_device, self.logger, self.state))
        self.run_coroutine(mqtt_publish_sesami_mode(self._mqtt, self.nuki_device, self.logger, self.mode))

    @property
    def logger(self) -> Logger:
        return self._logger

    @property
    def version(self) -> str:
        return self._version

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
        if state == DoorState.closed:
            self._door_opened = False
        self.logger.info("(state) %s -> %s", self._state.name, state.name)
        self._state = state
        self._state_changed = datetime.datetime.now(tz=datetime.UTC)
        if self._mqtt:
            self.run_coroutine(mqtt_publish_sesami_state(self._mqtt, self.nuki_device, self.logger, state))
            self.run_coroutine(mqtt_publish_sesami_mode(self._mqtt, self.nuki_device, self.logger, self.mode))

    @property
    def state_changed_time(self) -> datetime.datetime:
        return self._state_changed

    @property
    def mode(self) -> DoorMode:
        return DoorMode.openhold if self._state == DoorState.openhold else DoorMode.openclose

    @property
    def gpio_openhold_set(self) -> bool:
        return self._openhold_mode.value != 0

    def request_lock_action(self, action: NukiLockAction) -> None:
        self.logger.info("(lock) request action=%s", action.name)
        if self._mqtt:
            self.run_coroutine(mqtt_publish_nuki_lock_action(self._mqtt, self.nuki_device, self.logger, action))

    def unlatch(self) -> None:
        if self.lock == NukiLockState.unlatching:
            return
        self.logger.info("(unlatch) state=%s, lock=%s", self.state.name, self.lock.name)
        self.request_lock_action(NukiLockAction.unlatch)

    def open(self, trigger: DoorOpenTrigger) -> None:
        self.logger.info("(open) state=%s, lock=%s, trigger=%s", self.state.name, self.lock.name, trigger.name)
        self.logger.info("(relay) opendoor(blink 1[s])")
        self._opendoor.blink(on_time=1, off_time=1, n=1, background=True)
        if self._mqtt:
            self.run_coroutine(mqtt_publish_sesami_relay_opendoor_blink(self._mqtt, self.nuki_device, self.logger))

    def openhold(self, trigger: DoorOpenTrigger) -> None:
        self.logger.info("(openhold) state=%s, lock=%s, trigger=%s", self.state.name, self.lock.name, trigger.name)
        self.logger.info("(relay) openhold(1), openclose(0)")
        self._openhold_mode.on()
        self._openclose_mode.off()
        if self._mqtt:
            for name, state in [("opendoor", 0), ("openhold", 1), ("openclose", 0)]:
                self.run_coroutine(mqtt_publish_sesami_relay_state(self._mqtt, self.nuki_device, name, self.logger, state))
            self.run_coroutine(mqtt_publish_sesami_mode(self._mqtt, self.nuki_device, self.logger, DoorMode.openhold))

    def close(self) -> None:
        self.logger.info("(close) state=%s, lock=%s", self.state.name, self.lock.name)
        if self.lock in [NukiLockState.locked, NukiLockState.locking]:
            self.unlatch() # was unlock in original, but unlatch is used for opening.
        self.logger.info("(relay) openhold(0), openclose(1)")
        self._openhold_mode.off()
        self._openclose_mode.on()
        if self._mqtt:
            for name, state in [("opendoor", 0), ("openhold", 0), ("openclose", 1)]:
                self.run_coroutine(mqtt_publish_sesami_relay_state(self._mqtt, self.nuki_device, name, self.logger, state))
            self.run_coroutine(mqtt_publish_sesami_mode(self._mqtt, self.nuki_device, self.logger, DoorMode.openclose))

    def on_lock_state(self, lock: NukiLockState) -> None:
        self.logger.info("(lock_state) %s -> %s", self.lock.name, lock.name)
        self.lock = lock
        if lock == NukiLockState.unlatching:
            self.run_coroutine(timed_lock_unlatched(self, self._lock_unlatch_time))
        elif lock == NukiLockState.unlatched:
            self.on_lock_unlatched(DoorOpenTrigger.lock_unlatched)

    def on_lock_unlatched(self, trigger: DoorOpenTrigger) -> None:
        if self._door_opened:
            return
        self._door_opened = True
        if self.state == DoorState.openhold:
            self.openhold(trigger)
        else:
            self.open(trigger)

    def on_lock_action(self, action: NukiLockAction) -> None:
        self.logger.info("(lock_action) action=%s", action.name)
        self._nuki_action = action

    def on_lock_action_event(
        self, action: NukiLockAction, trigger: NukiLockTrigger, auth_id: int, code_id: int, auto_unlock: bool
    ) -> None:
        self.logger.info(
            "(lock_action_event) action=%s, trigger=%s, auth-id=%i, code-id=%i, auto-unlock=%i",
            action.name, trigger.name, auth_id, code_id, auto_unlock,
        )
        self._nuki_action_event = NukiLockActionEvent(action, trigger, auth_id, code_id, auto_unlock)

    def on_doorsensor_state(self, sensor: NukiDoorsensorState) -> None:
        self.logger.info("(doorsensor_state) %s -> %s", self.sensor.name, sensor.name)
        self.sensor = sensor
        if sensor == NukiDoorsensorState.door_closed and self.state == DoorState.opened:
            self.state = DoorState.closed
        if sensor == NukiDoorsensorState.door_opened and self.state == DoorState.closed:
            self.state = DoorState.opened

    def on_door_request(self, request: DoorRequestState) -> None:
        self.logger.info("(door_request) state=%s, lock=%s, request=%s", self.state.name, self.lock.name, request.name)
        if request == DoorRequestState.none:
            return
        if request == DoorRequestState.open:
            if self.state == DoorState.closed:
                self.state = DoorState.opened
                self.unlatch()
        elif request == DoorRequestState.close:
            if self.state == DoorState.openhold:
                self.state = DoorState.opened
                self.close()
        elif request == DoorRequestState.openhold and self.state != DoorState.openhold:
            self.state = DoorState.openhold
            self.unlatch()

    def on_pushbutton_pressed(self) -> None:
        self._strategy.on_pushbutton_pressed(self)


async def mqtt_receiver(client: aiomqtt.Client, door: ElectricDoor) -> None:
    async for msg in client.messages:
        payload = msg.payload.decode()
        topic = str(msg.topic)
        door.logger.info("[mqtt] receive %s=%s", topic, payload)
        if topic == f"nuki/{door.nuki_device}/state":
            door.on_lock_state(NukiLockState(int(payload)))
        elif topic == f"nuki/{door.nuki_device}/lockAction":
            door.on_lock_action(NukiLockAction(int(payload)))
        elif topic == f"nuki/{door.nuki_device}/lockActionEvent":
            ev = [int(e) for e in payload.split(",")]
            action = NukiLockAction(ev[0])
            trigger = NukiLockTrigger(ev[1])
            door.on_lock_action_event(action, trigger, ev[2], ev[3], bool(ev[4]))
        elif topic == f"nuki/{door.nuki_device}/doorsensorState":
            door.on_doorsensor_state(NukiDoorsensorState(int(payload)))
        elif topic == f"sesami/{door.nuki_device}/request/state":
            door.on_door_request(DoorRequestState(int(payload)))
