import logging
import os
import subprocess
import sys
from logging import Logger
from logging.handlers import RotatingFileHandler
from typing import List


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


def run(cmd: List[str], logger: Logger, check: bool):
    '''Runs a command and reirects stdout and stderr to the logger.

    Throws a subprocess.CalledProcessError when check is True and the command
    fails.

    Parameters:
    * cmd: command to run, e.g. ['ls', '-l']
    * logger: logger instance
    * check: True to throw an exception when the command fails
    
    '''
    logger.info("run '%s'", ' '.join(cmd) if isinstance(cmd, list) else cmd)
    try:
        proc = subprocess.run(cmd, check=check, capture_output=True)
        if proc.stdout:
            logger.info("%s", proc.stdout.decode())
        if proc.stderr:
            logger.error("%s", proc.stderr.decode())
    except subprocess.CalledProcessError as e:
        logger.exception("%s", e.stderr.decode())
        raise
    except FileNotFoundError as e:
        logger.exception("%s '%s'", e.strerror, e.filename)
        raise


def get_auth_fname() -> str:
    '''Returns the authentication file path (<prefix>/nuki-sesami/auth.json).

    When running in a virtual environment, the authentication file is expected
    in the virtual environment's etc directory.

    Otherwise the authentication file is expected in /etc.
    '''
    if is_virtual_env():
        return os.path.join(sys.prefix, 'etc', 'nuki-sesami', 'auth.json')
    else:
        return '/etc/nuki-sesami/auth.json'
