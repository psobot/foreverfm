import os
import logging
import threading

log = logging.getLogger(__name__)


class Brain(threading.Thread):
    def __init__(self, track_queue):
        self.track_queue = track_queue

        import brain
        self.brain = brain
        self.loaded = self.current_modtime

        threading.Thread.__init__(self)
        self.daemon = True

    @property
    def current_modtime(self):
        return os.path.getmtime(self.brain.__file__.replace("pyc", "py"))

    def run(self):
        g = self.brain.add_tracks()
        while True:
            if self.current_modtime != self.loaded:
                log.info("Hot-swapping brain! New choice generator started.")
                self.brain = reload(self.brain)
                self.loaded = self.current_modtime
                g = self.brain.add_tracks()

            track = g.next()
            log.info("Adding new track to queue.")
            self.track_queue.put(track)
