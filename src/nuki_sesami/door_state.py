#!/bin/env python3

from enum import IntEnum


class DoorState(IntEnum):
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


if __name__ == "__main__":
    import doctest
    doctest.testmod()
