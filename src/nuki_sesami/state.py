from enum import IntEnum


class DoorState(IntEnum):
    '''Current (internal) door controller state.

    >>> int(DoorState.closed) == 0
    True
    >>> int(DoorState.opened) == 1
    True
    >>> int(DoorState.openhold) == 2
    True
    '''
    closed      = 0
    '''Door is closed or closing'''
    opened      = 1
    '''Door is open or opening'''
    openhold    = 2
    '''Door is open or openning and will be held open'''


class DoorOpenTrigger(IntEnum):
    '''Indicates the reason for opening the door.

    >>> int(DoorOpenTrigger.unlatch_timeout) == 0
    True
    >>> int(DoorOpenTrigger.lock_unlatched) == 1
    True
    '''
    unlatch_timeout = 0
    '''Door opened due to a lock unlatch timeout'''
    lock_unlatched  = 1
    '''Door opened after the lock has unlatched'''

class DoorMode(IntEnum):
    '''Current operating mode of the doorcontroller.
    
    >>> int(DoorMode.openclose) == 0
    True
    >>> int(DoorMode.openhold) == 1
    True
    '''
    openclose       = 0
    '''Open the door for a brief moment and then close it again'''
    openhold        = 1
    '''Open the door and hold it open untill this mode ends'''


class DoorRequestState(IntEnum):
    '''Requested door state as received from Smartphone.

    >>> int(DoorRequestState.none) == 0
    True
    >>> int(DoorRequestState.close) == 1
    True
    >>> int(DoorRequestState.open) == 2
    True
    >>> int(DoorRequestState.openhold) == 3
    True
    '''
    none            = 0
    '''No request'''
    close           = 1
    '''Request to close the door'''
    open            = 2
    '''Request to open the door'''
    openhold        = 3
    '''Request to open the door and hold it open'''


class PushbuttonLogic(IntEnum):
    '''Defines how the pushbutton logic and how the door will react.
    
    >>> int(PushbuttonLogic.openhold) == 0
    True
    >>> int(PushbuttonLogic.open) == 1
    True
    >>> int(PushbuttonLogic.toggle) == 2
    True
    '''
    openhold    = 0
    '''Press once to open the door and hold it open, press again to
    close the door.'''
    open        = 1
    '''Press once to open the door, the door will close automatically
    after a short time.'''
    toggle      = 2
    '''Toggle between 'open' and 'openhold' door modes.'''


if __name__ == "__main__":
    import doctest
    doctest.testmod()
