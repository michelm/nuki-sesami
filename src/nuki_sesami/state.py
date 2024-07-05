from enum import IntEnum


class DoorState(IntEnum):
    """Current (internal) door controller state

    - closed = door is closed or closing,
    - open = door is open(ing).
    - openhold = door is open(ing) and will be held open.

    >>> int(DoorState.closed) == 0
    True
    >>> int(DoorState.opened) == 1
    True
    >>> int(DoorState.openhold) == 2
    True
    """
    closed      = 0 
    opened      = 1
    openhold    = 2


class DoorMode(IntEnum):
    """Current operating mode of the doorcontroller

    - openclose = door is open for a brief moment, the actual time is defined
    by the ERREKA 'Smart Evolution' electric door controller.
    - openhold = door will be held open until the pushbutton is pressed again.
    
    >>> int(DoorMode.openclose) == 0
    True
    >>> int(DoorMode.openhold) == 1
    True
    """
    openclose       = 0
    openhold        = 1


class DoorRequestState(IntEnum):
    """Requested door state as received from Smartphone

    - none = no request.
    - close = close the door.
    - open = open the door briefly and then close it.
    - openhold = open the door and hold it open.
    
    >>> int(DoorRequestState.none) == 0
    True
    >>> int(DoorRequestState.close) == 1
    True
    >>> int(DoorRequestState.open) == 2
    True
    >>> int(DoorRequestState.openhold) == 3
    True
    """
    none            = 0
    close           = 1
    open            = 2
    openhold        = 3


class PushbuttonLogic(IntEnum):
    """Defines how the pushbutton logic and how the door will react
    
    - openhold = press once to open the door and hold it open, press again to
    close the door.
    - open = press once to open the door, the door will close automatically
    after a short time.
    - toggle = toggle between 'open' and 'openhold' door modes.

    >>> int(PushbuttonLogic.openhold) == 0
    True
    >>> int(PushbuttonLogic.open) == 1
    True
    >>> int(PushbuttonLogic.toggle) == 2
    True
    """
    openhold    = 0
    open        = 1
    toggle      = 2


if __name__ == "__main__":
    import doctest
    doctest.testmod()
