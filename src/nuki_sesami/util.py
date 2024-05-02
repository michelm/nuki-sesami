import logging
import os
import subprocess
import sys
import json
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
    return '/etc/nuki-sesami/auth.json'


def get_username_password(auth_file: str, username: str, password: str) -> tuple[str, str]:
    '''Returns the (mqtt) username and password from the auth_file or the command line arguments.

    If username and/or password are not provided; i.e. are None, and the auth_file
    exists then the username and password from the auth_file will be used and returned.

    Parameters:
    * auth_file: str, the file name containing the username and password
    * username: str, the username from the command line arguments
    * password: str, the password from the command line arguments

    Returns:
    * username: str, the username
    * password: str, the password
    '''
    if not os.path.exists(auth_file):
        return username, password

    with open(auth_file) as f:
        auth = json.load(f)

    if username is None:
        username = auth['username']
    if password is None:
        password = auth['password']

    return username, password
