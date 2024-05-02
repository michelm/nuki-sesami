from enum import IntEnum


class DoorState(IntEnum):
    """Current (internal) door controller state

    >>> int(DoorState.openclose1) == 0
    True
    >>> int(DoorState.openclose2) == 1
    True
    >>> int(DoorState.openhold) == 2
    True
    """
    openclose1      = 0 # pushbutton is pressed 3 times; default state
    openclose2      = 1 # pushbutton is pressed once; request lock unlatched
    openhold        = 2 # pushbutton is pressed twice; change to openhold mode when lock unlatched


def next_door_state(state: DoorState) -> DoorState:
    """Returns the next door state based on the current door state

    >>> next_door_state(DoorState.openclose1).name
    'openclose2'
    >>> next_door_state(DoorState.openclose2).name
    'openhold'
    >>> next_door_state(DoorState.openhold).name
    'openclose1'
    """
    return DoorState((state + 1) % len(DoorState))


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


if __name__ == "__main__":
    import doctest
    doctest.testmod()
