from enum import IntEnum
import datetime

class NukiLockState(IntEnum):
    uncalibrated    = 0 # untrained
    locked          = 1 # online
    unlocking       = 2
    unlocked        = 3 # rto active
    locking         = 4
    unlatched       = 5 # open
    unlocked2       = 6 # lock-n-go
    unlatching      = 7 # opening
    boot_run        = 253
    motor_blocked   = 254
    undefined       = 255


class NukiLockAction(IntEnum):
    unlock          = 1 # activate rto
    lock            = 2 # deactivate rto
    unlatch         = 3 # electric strike actuation
    lock_and_go1    = 4 # lock&go; activate continuous mode
    lock_and_go2    = 5 # lock&go with unlatch deactivate continuous mode
    full_lock       = 6
    fob             = 80 # (without action) fob (without action)
    button          = 90 # (without action) button (without action)


class NukiDoorsensorState(IntEnum):
    deactivated         = 1 # door sensor not used
    door_closed         = 2
    door_opened         = 3
    door_state_unknown  = 4
    calibrating         = 5
    uncalibrated        = 16
    tampered            = 240
    unknown             = 255


class NukiLockTrigger(IntEnum):
    system_bluetooth    = 0
    reserved            = 1
    button              = 2
    automatic           = 3 # e.g. time controlled
    autolock            = 4
    homekit             = 171
    mqtt                = 172

class NukiLockActionEvent:
    '''Contains the last received lock action event from the Nuki smart lock
    '''
    def __init__(self, state: NukiLockState, trigger: NukiLockTrigger, auth_id: int, code_id: int, auto_unlock: bool):
        self.state = state
        self.trigger = trigger
        self.auth_id = auth_id
        self.code_id = code_id
        self.auto_unlock = auto_unlock
        self.timestamp = datetime.datetime.now()
