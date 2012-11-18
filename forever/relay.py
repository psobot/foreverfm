"""
Forever.fm Bandwidth Relay
by @psobot, Nov 17 2012
"""

import config
import apikeys
import customlog
import logging

import os
import sys
import time
import Queue
import socket
import restart
import urllib2
import datetime
import traceback
import threading
import tornado.web
import tornado.ioloop
import tornado.template
from daemon import Daemon
from functools import partial

started_at_timestamp = time.time()
r = urllib2.urlopen(config.primary_url)

class StreamHandler(tornado.web.RequestHandler):
    listeners = []

    @classmethod
    def stream_frames(cls):
        l = tornado.ioloop.IOLoop.instance()
        while True:
            try:
                l.add_callback(partial(cls.broadcast, r.read(256)))
            except:
                try:
                    r = urllib2.urlopen(config.primary_url)
                except:
                    log.error("Could not reopen stream!\n%s", traceback.format_exc())

    @classmethod
    def broadcast(cls, packet):
        for i, listener in enumerate(cls.listeners):
            if listener.request.connection.stream.closed():
                try:
                    listener.finish()
                except:
                    pass
            else:
                listener.write(packet)
                listener.flush()


    @tornado.web.asynchronous
    def get(self):
        ip = self.request.headers.get('X-Real-Ip', self.request.remote_ip)
        log.info("Added new listener at %s", ip)
        self.set_header("Content-Type", "audio/mpeg")
        self.listeners.append(self)

    def on_finish(self):
        ip = self.request.headers.get('X-Real-Ip', self.request.remote_ip)
        log.info("Removed listener at %s", ip)
        self.listeners.remove(self)


if __name__ == "__main__":
    Daemon()

    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)
    logging.root.addHandler(customlog.MultiprocessingStreamHandler())
    log = logging.getLogger(config.log_name)

    log.info("Starting %s relay...", config.app_name)

    tornado.ioloop.PeriodicCallback(
        lambda: restart.check('restart.txt',
                              started_at_timestamp,
                              len(StreamHandler.listeners)),
        config.restart_timeout * 1000
    ).start()

    application = tornado.web.Application([
        (r"/all.mp3", StreamHandler)
    ])

    frame_sender = threading.Thread(target=StreamHandler.stream_frames)
    frame_sender.daemon = True
    frame_sender.start()

    application.listen(config.http_port)
    tornado.ioloop.IOLoop.instance().start()
