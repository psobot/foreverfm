import sys
import time
import Queue
import config
import logging
from cube import emit
from restart import RESTART_EXIT_CODE

LAG_LIMIT = config.lag_limit
log = logging.getLogger(config.log_name)
log.setLevel(logging.DEBUG)


class Listeners(list):
    def __init__(self, queue, name, semaphore):
        self.queue = queue
        self.__name = name
        self.__packet = None
        self.__first_send = None
        self.__count = 0L
        self.__drift_limit = config.drift_limit
        self.__semaphore = semaphore
        list.__init__(self)

    def append(self, listener):
        if self.__packet:
            listener.write(self.__packet)
            listener.flush()
        list.append(self, listener)

    def broadcast(self):
        try:
            now = time.time()
            self.__broadcast()
            if not self.__first_send:
                log.info("Sending first frame for %s.", self.__name)
                self.__first_send = time.time()
                self.__semaphore.release()

            uptime = float(now - self.__first_send)
            if self.__count > 0 and not self.__count % 30:
                samples = self.__count * 1152
                duration = float(self.__count) * 1152.0 / 44100.0
                buffered = self.queue.buffered
                emit('drift', {
                    'ms': (duration - uptime) * 1000.0,
                    'rate': (duration / uptime),
                })
                emit('buffered', {
                    'queue': self.__name,
                    'frames': buffered,
                })
                if self.__count > 0 and not self.__count % 2296:
                    log.debug("Sent %d frames (%dsam, %fs) over %fs (%fx).",
                            self.__count, samples, duration, uptime,
                            duration / uptime)

            if (float(self.__count) * 1152.0 / 44100.0) \
                    + self.__drift_limit < uptime:
                log.warning("Queue %s drifting by %2.2f ms. Compensating...",
                    self.__name,
                    1000 * (uptime - (float(self.__count) * 1152.0 / 44100.0))
                )
                while (float(self.__count) * 1152.0 / 44100.0) < uptime:
                    self.__broadcast()
        except Queue.Empty:
            if self.__packet and not self.__starving:
                self.__starving = True
                log.critical("Dropping frames! Queue %s is starving!", self.__name)
                log.critical("Committing suicide.")
                sys.exit(RESTART_EXIT_CODE)

    def __broadcast(self):
        self.__packet = self.queue.get_nowait()
        self.__count += 1
        self.__starving = False
        for i, listener in enumerate(list(self)):
            if listener.request.connection.stream.closed():
                try:
                    listener.finish()
                except (AssertionError, IOError, RuntimeError):
                    try:
                        self.remove(listener)
                    except:
                        pass
            else:
                listener.write(self.__packet)
                listener.flush()
