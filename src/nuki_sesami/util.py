import logging
import os
import subprocess
import sys
from logging import Logger
from logging.handlers import RotatingFileHandler


def is_virtual_env() -> bool:
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

    Returns:
    * logger: logger instance
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


def run(cmd: list[str], logger: Logger, check: bool) -> None:
    '''Runs a command and redirects stdout and stderr to the logger.

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


def get_prefix() -> str:
    if os.geteuid() == 0:
        return '/'
    if is_virtual_env():
        return sys.prefix
    return os.path.join(os.path.expanduser('~'), '.local')


def get_config_path() -> str:
    if os.geteuid() == 0:
        return '/etc/nuki-sesami'
    if is_virtual_env():
        return os.path.join(sys.prefix, 'etc', 'nuki-sesami')
    return os.path.join(os.path.expanduser('~'), '.config', 'nuki-sesami')

