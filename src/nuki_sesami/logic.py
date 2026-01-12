from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from nuki_sesami.state import DoorState

if TYPE_CHECKING:
    from nuki_sesami.door import ElectricDoor


class PushbuttonStrategy(ABC):
    """Abstract base class for pushbutton logic strategies."""

    @abstractmethod
    def on_pushbutton_pressed(self, door: ElectricDoor) -> None:
        """Called when the pushbutton is pressed."""
        pass


class OpenHoldStrategy(PushbuttonStrategy):
    """Press once to open the door and hold it open, press again to close."""

    def on_pushbutton_pressed(self, door: ElectricDoor) -> None:
        door.logger.info(
            "(%s.pushbutton_pressed) state=%s, lock=%s",
            type(self).__name__,
            door.state.name,
            door.lock.name,
        )
        next_state = DoorState.openhold if door.state == DoorState.closed else DoorState.closed
        door.state = next_state
        if door.state == DoorState.openhold:
            door.unlatch()  # open the door once lock is unlatched
        else:
            door.close()


class OpenStrategy(PushbuttonStrategy):
    """Press once to open the door briefly."""

    def on_pushbutton_pressed(self, door: ElectricDoor) -> None:
        door.logger.info(
            "(%s.pushbutton_pressed) state=%s, lock=%s",
            type(self).__name__,
            door.state.name,
            door.lock.name,
        )
        door.state = DoorState.opened
        door.unlatch()  # open the door once lock is unlatched


class ToggleStrategy(PushbuttonStrategy):
    """Toggle between 'open' and 'openhold' door modes."""

    def on_pushbutton_pressed(self, door: ElectricDoor) -> None:
        door.logger.info(
            "(%s.pushbutton_pressed) state=%s, lock=%s",
            type(self).__name__,
            door.state.name,
            door.lock.name,
        )
        next_state = DoorState((door.state + 1) % len(DoorState))
        door.state = next_state
        if door.state == DoorState.closed:
            door.unlatch()  # open the door once lock is unlatched
        elif door.state == DoorState.opened:
            door.close()
        elif door.state == DoorState.openhold:
            pass  # no action here
