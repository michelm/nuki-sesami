import datetime
from enum import IntEnum


class NukiLockState(IntEnum):
    """Current state of the lock.

    >>> int(NukiLockState.uncalibrated) == 0
    True
    >>> int(NukiLockState.locked) == 1
    True
    >>> int(NukiLockState.unlocking) == 2
    True
    >>> int(NukiLockState.unlocked) == 3
    True
    >>> int(NukiLockState.locking) == 4
    True
    >>> int(NukiLockState.unlatched) == 5
    True
    >>> int(NukiLockState.unlocked2) == 6
    True
    >>> int(NukiLockState.unlatching) == 7
    True
    >>> int(NukiLockState.boot_run) == 253
    True
    >>> int(NukiLockState.motor_blocked) == 254
    True
    >>> int(NukiLockState.undefined) == 255
    True
    """

    uncalibrated = 0
    """The lock is uncalibrated and needs to be trained."""
    locked = 1
    """The lock is online and in locked state."""
    unlocking = 2
    unlocked = 3
    """(RTO active) Door can be opened when user unlatches using the door handle."""
    locking = 4
    unlatched = 5
    """The lock is inlatched and the door can be opened."""
    unlocked2 = 6
    """The lock is in unlocked state in 'lock&go' mode."""
    unlatching = 7
    boot_run = 253
    motor_blocked = 254
    undefined = 255


class NukiLockAction(IntEnum):
    """Used for requesting the lock to change state.

    >>> int(NukiLockAction.unlatch) == 1
    True
    >>> int(NukiLockAction.lock) == 2
    True
    >>> int(NukiLockAction.unlatch) == 3
    True
    >>> int(NukiLockAction.lock_and_go1) == 4
    True
    >>> int(NukiLockAction.lock_and_go2) == 5
    True
    >>> int(NukiLockAction.full_lock) == 6
    True
    >>> int(NukiLockAction.fob) == 80
    True
    >>> int(NukiLockAction.button) == 90
    True
    """

    unlock = 1
    """Request unlocked state; activates RTO."""
    lock = 2
    """Request locked state; deactivates RTO."""
    unlatch = 3
    """Request lock electric strike actuation"""
    lock_and_go1 = 4
    """Request lock&go; activates continuous mode"""
    lock_and_go2 = 5
    """Request lock&go with unlatch; deactivates continuous mode"""
    full_lock = 6
    fob = 80
    """'without action"""
    button = 90
    """without action)"""


class NukiDoorsensorState(IntEnum):
    """Current state of the door sensor.

    >>> int(NukiDoorsensorState.door_closed) == 2
    True
    >>> int(NukiDoorsensorState.door_opened) == 3
    True
    >>> int(NukiDoorsensorState.door_state_unknown) == 4
    True
    >>> int(NukiDoorsensorState.calibrating) == 5
    True
    >>> int(NukiDoorsensorState.uncalibrated) == 16
    True
    >>> int(NukiDoorsensorState.tampered) == 240
    True
    >>> int(NukiDoorsensorState.unknown) == 255
    True
    """

    deactivated = 1
    """Door sensor is not used"""
    door_closed = 2
    door_opened = 3
    door_state_unknown = 4
    calibrating = 5
    uncalibrated = 16
    tampered = 240
    unknown = 255


class NukiLockTrigger(IntEnum):
    """Indicates the trigger of the lock action.

    >>> int(NukiLockTrigger.system_bluetooth) == 0
    True
    >>> int(NukiLockTrigger.reserved) == 1
    True
    >>> int(NukiLockTrigger.button) == 2
    True
    >>> int(NukiLockTrigger.automatic) == 3
    True
    >>> int(NukiLockTrigger.autolock) == 6
    True
    >>> int(NukiLockTrigger.homekit) == 171
    True
    >>> int(NukiLockTrigger.mqtt) == 172
    True
    """

    system_bluetooth = 0
    reserved = 1
    button = 2
    automatic = 3
    """e.g. time controlled"""
    autolock = 6
    homekit = 171
    mqtt = 172


class NukiLockActionEvent:
    """Contains the last received lock action event from the Nuki smart lock.

    >>> event = NukiLockActionEvent(
    ...     NukiLockAction.unlatch, NukiLockTrigger.button, 1, 2, 3
    ... )
    >>> event.action == NukiLockAction.unlatch
    True
    >>> event.trigger == NukiLockTrigger.button
    True
    >>> event.auth_id == 1
    True
    >>> event.code_id == 2
    True
    >>> event.auto_unlock == 3
    True
    """

    action: NukiLockAction
    """Request lock action; e.g. unlatch"""

    trigger: NukiLockTrigger
    """Trigger source of the event; e.g. bluetooth"""

    auth_id: int
    """Authorization ID of the user"""

    code_id: int
    """ID of the Keypad code, 0 = unknown"""

    auto_unlock: int
    """Auto-Unlock (0 or 1) or number of button presses (only button & fob actions) or
    Keypad source (0 = back key, 1 = code, 2 = fingerprint)"""

    timestamp: datetime.datetime
    """Timestamp of the event"""

    def __init__(self, action: NukiLockAction, trigger: NukiLockTrigger, auth_id: int, code_id: int, auto_unlock: int):
        self.action = action
        self.trigger = trigger
        self.auth_id = auth_id
        self.code_id = code_id
        self.auto_unlock = auto_unlock
        self.timestamp = datetime.datetime.now(tz=datetime.UTC)


if __name__ == "__main__":
    import doctest

    doctest.testmod()
