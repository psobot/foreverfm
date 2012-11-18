"""
Forever.fm Bandwidth Relay
by @psobot, Nov 17 2012
"""

import config
import customlog
import logging

import time
import restart
import urllib2
import traceback
import threading
import tornado.web
import tornado.ioloop
import tornado.template
from daemon import Daemon

if __name__ == "__main__":
    Daemon()
    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)
    logging.root.addHandler(customlog.MultiprocessingStreamHandler())
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)

started_at_timestamp = time.time()
log.info("Opening stream %s", config.primary_url)
r = urllib2.urlopen(config.primary_url)
log.info("Opened stream!")
PACKET_SIZE = config.packet_size


class StreamHandler(tornado.web.RequestHandler):
    listeners = []
    __packet = ""
    recv = 0L
    sent = 0L

    @classmethod
    def stream_frames(cls):
        global r
        while True:
            try:
                cls.__packet = r.read(PACKET_SIZE)
                cls.recv += len(cls.__packet)
                for i, listener in enumerate(cls.listeners):
                    if listener.request.connection.stream.closed():
                        try:
                            listener.finish()
                        except:
                            cls.listeners.remove(listener)
                    else:
                        listener.write(cls.__packet)
                        listener.flush()
                cls.sent += len(cls.__packet)
            except urllib2.URLError:
                log.error("Got error:\n%s", traceback.format_exc())
                try:
                    log.info("Reopening stream.")
                    r = urllib2.urlopen(config.primary_url)
                except:
                    log.error("Could not reopen stream!\n%s", traceback.format_exc())
            except:
                log.error("Major failure in stream_frames:\n%s", traceback.format_exc())

    @tornado.web.asynchronous
    def get(self):
        try:
            ip = self.request.headers.get('X-Real-Ip', self.request.remote_ip)
            log.info("Added new listener at %s", ip)
            self.set_header("Content-Type", "audio/mpeg")
            self.write(self.__packet)
            self.listeners.append(self)
        except:
            log.error("%s", traceback.format_exc())
            tornado.web.RequestHandler.send_error(self, 500)

    def on_finish(self):
        try:
            ip = self.request.headers.get('X-Real-Ip', self.request.remote_ip)
            log.info("Removed listener at %s", ip)
            self.listeners.remove(self)
        except:
            log.error("%s", traceback.format_exc())


class InfoHandler(tornado.web.RequestHandler):
    def get(self):
        try:
            self.set_header("Content-Type", "application/json")
            self.finish({
                "listeners": {
                    "count": len(StreamHandler.listeners),
                    "ips": [l.request.headers.get('X-Real-Ip', l.request.remote_ip)
                               for l in StreamHandler.listeners]
                },
                "packets": {
                    "sent": StreamHandler.sent,
                    "recv": StreamHandler.recv
                }
            })
        except:
            log.error("%s", traceback.format_exc())
            tornado.web.RequestHandler.send_error(self, 500)


def update():
    global PACKET_SIZE
    PACKET_SIZE = config.packet_size


if __name__ == "__main__":
    log.info("Starting %s relay...", config.app_name)

    tornado.ioloop.PeriodicCallback(
        lambda: restart.check('restart.txt',
                              started_at_timestamp,
                              len(StreamHandler.listeners)),
        config.restart_timeout * 1000
    ).start()
    tornado.ioloop.PeriodicCallback(update, 5000).start()

    application = tornado.web.Application([
        (r"/all.mp3", StreamHandler),
        (r"/", InfoHandler)
    ])

    frame_sender = threading.Thread(target=StreamHandler.stream_frames)
    frame_sender.daemon = True
    frame_sender.start()

    application.listen(config.http_port)
    tornado.ioloop.IOLoop.instance().start()
