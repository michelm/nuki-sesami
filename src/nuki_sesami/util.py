import os
import sys
import logging
from logging import Logger
from logging.handlers import RotatingFileHandler
from typing import List
import subprocess


def is_virtual_env():
    '''Returns true when running in a virtual environment.'''
    return sys.prefix != sys.base_prefix


def getlogger(name: str, path: str, level: int = logging.INFO) -> Logger:
    '''Returns a logger instance for the given name and path.

    The logger for will rotating log files with a maximum size of 1MB and
    a maximum of 10 log files.

    Parameters:
    * name: name of the logger, e.g. 'nuki-sesami'
    * path: complete path for storing the log files, e.g. '/var/log/nuki-sesami'
    * level: logging level, e.g; logging.DEBUG

    '''
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    handler = RotatingFileHandler(f'{os.path.join(path,name)}.log', maxBytes=1048576, backupCount=10)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    return logger


def exec(cmd: List[str] | str, logger: Logger, check: bool = True):
    '''Runs a command and reirects stdout and stderr to the logger.

    Throws a subprocess.CalledProcessError when check is True and the command
    fails.
    '''
    logger.info("run '%s'", ' '.join(cmd) if isinstance(cmd, list) else cmd)
    try:
        proc = subprocess.run(cmd, check=check, capture_output=True)
        if proc.stdout:
            logger.info("%s", proc.stdout.decode())
        if proc.stderr:
            logger.error("%s", proc.stderr.decode())
    except subprocess.CalledProcessError as e:
        logger.error("%s", e.stderr.decode())
        raise e
    except FileNotFoundError as e:
        logger.error("%s '%s'", e.strerror, e.filename)
        raise e

