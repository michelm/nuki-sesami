from enum import IntEnum


class DoorState(IntEnum):
    """Current (internal) door controller state

    >>> int(DoorState.closed) == 0
    True
    >>> int(DoorState.opened) == 1
    True
    >>> int(DoorState.openhold) == 2
    True
    """
    closed      = 0 # door is closed or about to close
    opened      = 1 # door is open(ing)
    openhold    = 2 # door is open(ing) and will be held open


class DoorMode(IntEnum):
    """Current operating mode of the doorcontroller

    >>> int(DoorMode.openclose) == 0
    True
    >>> int(DoorMode.openhold) == 1
    True
    """
    openclose       = 0 # door is open for a brief moment, the actual time is defined by the
                        # ERREKA 'Smart Evolution' electric door controller
    openhold        = 1 # door will be held open until the pushbutton is pressed again


class DoorRequestState(IntEnum):
    """Requested door state as received from Smartphone

    >>> int(DoorRequestState.none) == 0
    True
    >>> int(DoorRequestState.close) == 1
    True
    >>> int(DoorRequestState.open) == 2
    True
    >>> int(DoorRequestState.openhold) == 3
    True
    """
    none            = 0 # no request
    close           = 1 # close the door
    open            = 2 # open the door briefly and then close it
    openhold        = 3 # open the door and hold it open


class PushbuttonLogic(IntEnum):
    openhold    = 0
    open        = 1
    toggle      = 2 # toggle between 'open' and 'openhold' door modes


if __name__ == "__main__":
    import doctest
    doctest.testmod()
