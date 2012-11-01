import tornadio2
import traceback
import logging

__author__ = 'psobot'
log = logging.getLogger(__name__)


class SocketHandler(tornadio2.conn.SocketConnection):
    listeners = set()

    @classmethod
    def on_data(self, data):
        try:
            if self.listeners:
                for i, l in enumerate(self.listeners.copy()):
                    try:
                        l.send(data)
                    except:
                        log.error(
                            "Failed to send data to listener %d due to:\n%s",
                            i, traceback.format_exc()
                        )
                        self.listeners.remove(l)
        except:
            log.error("Could not update listeners due to:\n%s",
                      traceback.format_exc())

    def on_open(self, *args, **kwargs):
        log.info("Opened socket.")
        self.listeners.add(self)

    def on_close(self):
        log.info("Closed socket.")
        self.listeners.remove(self)

    def on_message(self, message):
        pass
