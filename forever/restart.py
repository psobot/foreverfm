__author__ = 'psobot'

import os
import sys
import logging
import subprocess
log = logging.getLogger(__name__)

RESTART_EXIT_CODE = 123


def check(f, t):
    import wm
    if not os.path.isfile(f):
        return
    if os.stat(f).st_mtime > t:
        if not wm.rq.pending_restart:
            log.info("Closing frontend due to pending restart.")
            wm.rq.pending_restart = True
        if len(wm.rq.running) or len(wm.rq.queue):
            log.warning(
                "Could not restart server due to %d remixes running and %d in queue.",
                len(wm.rq.running), len(wm.rq.queue)
            )
        else:
            log.fatal("Restarting server...")
            sys.exit(RESTART_EXIT_CODE)


def loop():
    command = "python -m forever.server"

    retval = RESTART_EXIT_CODE
    while retval == RESTART_EXIT_CODE:
        retval = subprocess.call(command.split())
