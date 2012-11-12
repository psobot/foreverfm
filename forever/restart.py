__author__ = 'psobot'

import os
import sys
import logging
import traceback
import subprocess
log = logging.getLogger(__name__)

RESTART_EXIT_CODE = 123


def check(f, t, l):
    try:
        if not os.path.isfile(f):
            return
        if os.stat(f).st_mtime > t:
            if l:
                log.warning(
                    "Pending restart, waiting for %d listeners to exit.", l
                )
            else:
                log.fatal("Restarting server...")
                sys.exit(RESTART_EXIT_CODE)
    except Exception:
        log.error("Could not check restart:\n%s", traceback.format_exc())


def loop():
    command = "python -m forever.server"

    retval = RESTART_EXIT_CODE
    while retval == RESTART_EXIT_CODE:
        retval = subprocess.call(command.split())
