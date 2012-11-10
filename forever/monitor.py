import os
import time
import config
import logging
import traceback
import tornadio2
import tornado.web
from assetcompiler import compiled

templates = tornado.template.Loader(config.template_dir)
templates.autoescape = None

log = logging.getLogger(__name__)
started = time.time()


class MonitorHandler(tornado.web.RequestHandler):
    mtime = 0
    template = "monitor.html"

    def get(self):
        try:
            if os.path.getmtime(config.template_dir + self.template) > self.mtime:
                templates.reset()
                self.mtime = time.time()
            kwargs = {
                "start_time": started,
                'compiled': compiled
            }
            self.write(templates.load(self.template).generate(**kwargs))
        except Exception, e:
            log.error(e)
            tornado.web.RequestHandler.send_error(self, 500)


class MonitorSocket(tornadio2.conn.SocketConnection):
    monitors = set()
    data = {}

    @classmethod
    def update(self, data):
        self.data = data
        self.broadcast()

    @classmethod
    def broadcast(self):
        for i, m in enumerate(self.monitors.copy()):
            try:
                m.send(self.data)
            except:
                log.error(
                    "Failed to send data to monitor %d due to:\n%s",
                    i, traceback.format_exc()
                )
                self.monitors.remove(m)

    def on_open(self, *args, **kwargs):
        log.info("Opened monitor socket.")
        self.monitors.add(self)
        self.update(self.data)

    def on_close(self):
        log.info("Closed monitor socket.")
        self.monitors.remove(self)

    def on_message(self, message):
        pass
