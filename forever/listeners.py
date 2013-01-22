import sys
import time
import lame
import Queue
import config
import logging
from restart import RESTART_EXIT_CODE

LAG_LIMIT = config.lag_limit
log = logging.getLogger(config.log_name)
log.setLevel(logging.DEBUG)


class Listeners(list):
    def __init__(self, queue, name, semaphore):
        self.queue = queue
        self.__name = name
        self.__packet = None
        self.__last_send = None
        self.__first_send = None
        self.__lag = 0
        self.__count = 0L
        self.__semaphore = semaphore
        list.__init__(self)

    def append(self, listener):
        if self.__packet:
            listener.write(self.__packet)
            listener.flush()
        list.append(self, listener)

    def broadcast(self):
        try:
            if self.__lag > LAG_LIMIT:
                log.error("Lag (%s) exceeds limit - dropping frames!",
                          self.__lag)
                self.__lag = 0

            self.__broadcast()
            if self.__last_send:
                self.__lag += int((time.time() - self.__last_send) * 44100)\
                                - lame.SAMPLES_PER_FRAME
            else:
                log.info("Sending first frame for %s.", self.__name)
                self.__first_send = time.time()
                self.__semaphore.release()

            if self.__lag > 0:
                log.warning("Queue %s lag detected. (%2.2f ms)",
                            self.__name, (self.__lag * 1000.0 / 44100.0))
                while self.__lag > 0 and not self.queue.empty():
                    self.__broadcast()
                    self.__lag -= lame.SAMPLES_PER_FRAME
                log.warning("Queue %s lag compensated. Leading by %2.2f ms.",
                            self.__name, (self.__lag *  -1000.0 / 44100.0))

            self.__last_send = time.time()

            if self.__count > 0 and not self.__count % 2296:
                now = time.time()
                uptime = float(now - self.__first_send)
                duration = float(self.__count) * 1152.0 / 44100.0
                log.debug("Sent %d frames (%dsam, %fs) over %fs (%fx).",
                          self.__count, self.__count * 1152, duration, uptime,
                          duration / uptime)
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
