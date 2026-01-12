from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import logging
import os
import sys
from logging import Logger

import aiomqtt

from nuki_sesami.config import SesamiConfig, get_config
from nuki_sesami.door import ElectricDoor, mqtt_receiver
from nuki_sesami.logic import OpenHoldStrategy, OpenStrategy, ToggleStrategy
from nuki_sesami.state import PushbuttonLogic
from nuki_sesami.util import get_config_path, get_prefix, getlogger, mqtt_retry_loop


async def activate(logger: Logger, config: SesamiConfig, version: str) -> None:
    """Activates the electric door service."""
    if config.pushbutton == PushbuttonLogic.open:
        strategy = OpenStrategy()
    elif config.pushbutton == PushbuttonLogic.toggle:
        strategy = ToggleStrategy()
    else:
        strategy = OpenHoldStrategy()

    door = ElectricDoor(logger, config, version, strategy)

    async for attempt in mqtt_retry_loop(logger):
        try:
            async with aiomqtt.Client(
                config.mqtt_host, port=config.mqtt_port, username=config.mqtt_username, password=config.mqtt_password
            ) as client:
                loop = asyncio.get_running_loop()
                door.activate(client, loop)
                device = door.nuki_device
                await client.subscribe(f"nuki/{device}/state")
                await client.subscribe(f"nuki/{device}/lockAction")
                await client.subscribe(f"nuki/{device}/lockActionEvent")
                await client.subscribe(f"nuki/{device}/doorsensorState")
                await client.subscribe(f"sesami/{device}/request/state")
                await mqtt_receiver(client, door)
        except aiomqtt.MqttError:
            logger.error("mqtt connection failed (attempt %i)", attempt)


def main():
    parser = argparse.ArgumentParser(
        prog="nuki-sesami",
        description="Open and close an electric door equipped with a Nuki 3.0 pro smart lock",
        epilog="Belrog: you shall not pass!",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("-p", "--prefix", help="runtime system root; e.g. '~/.local' or '/'", type=str, default=None)
    parser.add_argument(
        "-c",
        "--cpath",
        help="configuration path; e.g. '/etc/nuki-sesami' or '~/.config/nuki-sesami'",
        type=str,
        default=None,
    )
    parser.add_argument("-V", "--verbose", help="be verbose", action="store_true")
    parser.add_argument("-v", "--version", help="print version and exit", action="store_true")

    args = parser.parse_args()
    version = importlib.metadata.version("nuki-sesami")
    if args.version:
        print(version)  # noqa: T201
        sys.exit(0)

    prefix = args.prefix or get_prefix()
    cpath = args.cpath or get_config_path()
    logpath = os.path.join(prefix, "var/log/nuki-sesami")

    if not os.path.exists(logpath):
        os.makedirs(logpath)

    logger = getlogger("nuki-sesami", logpath, level=logging.DEBUG if args.verbose else logging.INFO)
    config = get_config(cpath)

    logger.info("version          : %s", version)
    logger.info("prefix           : %s", prefix)
    logger.info("config-path      : %s", cpath)
    logger.info("pushbutton       : %s", config.pushbutton.name)
    logger.info("nuki.device      : %s", config.nuki_device)
    logger.info("mqtt.host        : %s", config.mqtt_host)
    logger.info("mqtt.port        : %i", config.mqtt_port)
    logger.info("mqtt.username    : %s", config.mqtt_username)
    logger.info("mqtt.password    : %s", "***")
    logger.info("gpio.pushbutton  : %s", config.gpio_pushbutton)
    logger.info("gpio.opendoor    : %s", config.gpio_opendoor)
    logger.info("gpio.openhold    : %s", config.gpio_openhold_mode)
    logger.info("gpio.openclose   : %s", config.gpio_openclose_mode)
    logger.info("door-open-time   : %i", config.door_open_time)
    logger.info("door-close-time  : %i", config.door_close_time)
    logger.info("lock-unlatch-time: %i", config.lock_unlatch_time)

    try:
        asyncio.run(activate(logger, config, version))
    except KeyboardInterrupt:
        logger.info("program terminated; keyboard interrupt")
    except Exception:
        logger.exception("something went wrong, exception")


if __name__ == "__main__":
    main()
