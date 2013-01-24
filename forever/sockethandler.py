import json
import logging
import tornadio2
import traceback

__author__ = 'psobot'
log = logging.getLogger(__name__)


class SocketHandler(tornadio2.conn.SocketConnection):
    listeners = set()

    @classmethod
    def on_segment(self, data):
        try:
            data = json.dumps({"segment": data},
                              ensure_ascii=False).encode('utf-8')
            if self.listeners:
                for i, l in enumerate(self.listeners.copy()):
                    try:
                        l.send(data)
                    except:
                        log.error(
                            "Failed to send data to socket %d due to:\n%s",
                            i, traceback.format_exc()
                        )
                        self.listeners.remove(l)
        except:
            log.error("Could not update sockets due to:\n%s",
                      traceback.format_exc())

    @classmethod
    def on_listener_change(self, mp3_listeners):
        try:
            data = json.dumps({"listener_count": len(mp3_listeners)},
                              ensure_ascii=False).encode('utf-8')
            if self.listeners:
                for i, l in enumerate(self.listeners.copy()):
                    try:
                        l.send(data)
                    except:
                        log.error(
                            "Failed to send data to socket %d due to:\n%s",
                            i, traceback.format_exc()
                        )
                        self.listeners.remove(l)
        except:
            log.error("Could not update sockets due to:\n%s",
                      traceback.format_exc())

    def on_open(self, *args, **kwargs):
        self.listeners.add(self)

    def on_close(self):
        self.listeners.remove(self)

    def on_message(self, message):
        pass
