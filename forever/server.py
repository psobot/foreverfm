"""
Forever.fm Server
by @psobot, Nov 3 2012
"""

import config
import apikeys
import customlog
import logging

import os
import sys
import json
import lame
import time
import info
import restart
import datetime
import traceback
import tornado.web
import statistician
import tornado.ioloop
import tornado.template
import tornadio2.server
import multiprocessing
import pyechonest.config

from mixer import Mixer
from daemon import Daemon
from hotswap import Hotswap
from listeners import Listeners
from assetcompiler import compiled
from sockethandler import SocketHandler
from bufferedqueue import BufferedReadQueue
from monitor import MonitorHandler, MonitorSocket

#   API Key setup
pyechonest.config.ECHO_NEST_API_KEY = apikeys.ECHO_NEST_API_KEY

started_at_timestamp = time.time()
started_at = datetime.datetime.utcnow()

test = 'test' in sys.argv
frontend = 'frontend' in sys.argv
stream = not frontend
SECONDS_PER_FRAME = lame.SAMPLES_PER_FRAME / 44100.0

templates = tornado.template.Loader(config.template_dir)
templates.autoescape = None


class MainHandler(tornado.web.RequestHandler):
    mtime = 0
    template = 'index.html'

    def __gen(self):
        debug = self.get_argument('__debug', None)
        if debug is None:
            debug = self.request.host.startswith("localhost")
        else:
            debug = debug in ["True", 1, "on"]
        kwargs = {
            'debug': debug,
            'compiled': compiled,
        }
        try:
            if os.path.getmtime(config.template_dir + self.template) > self.mtime:
                templates.reset()
                self.mtime = time.time()
            return templates.load(self.template).generate(**kwargs)
        except Exception, e:
            log.error(e)
            tornado.web.RequestHandler.send_error(self, 500)
            return

    def head(self):
        self.__gen()
        self.finish()

    def get(self):
        self.finish(self.__gen())


class InfoHandler(tornado.web.RequestHandler):
    actions = []

    @classmethod
    def add(self, data):
        self.clean()
        self.actions.append(data)
        SocketHandler.on_data(data)

    @classmethod
    def clean(cls):
        try:
            now = time.time()
            while cls.actions and cls.actions[0]['time'] \
               + cls.actions[0]['duration'] + config.past_played_buffer < now:
                cls.actions.pop(0)
        except:
            log.error("Error while cleaning up:\n%s", traceback.format_exc())

    def get(self):
        self.set_header("Content-Type", "application/json")
        try:
            self.write(json.dumps(self.actions, ensure_ascii=False).encode('utf-8'))
        except:
            log.error("Could not send info burst:\n%s", traceback.format_exc())
            self.write(json.dumps([]))


class StreamHandler(tornado.web.RequestHandler):
    __subclasses = []
    listeners = []

    @classmethod
    def get_queues(cls):
        return [k.listeners.queue for k in cls.__subclasses]

    @classmethod
    def stream_frames(cls):
        for klass in cls.__subclasses:
            try:
                klass.listeners.broadcast()
            except:
                log.error("Could not broadcast due to: \n%s", traceback.format_exc())

    @classmethod
    def init_streams(cls, streams):
        routes = []
        for endpoint, name, q in streams:
            klass = type(
                name + "Handler",
                (StreamHandler,),
                {"listeners": Listeners(q, name)}
            )
            cls.__subclasses.append(klass)
            routes.append((endpoint, klass))
        return routes

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


class SocketConnection(tornadio2.conn.SocketConnection):
    __endpoints__ = {
        "/info.websocket": SocketHandler,   #TODO: Rename
        "/monitor.websocket": MonitorSocket
    }


def get_listeners():
    try:
        return sum([x.listeners for x in StreamHandler._StreamHandler__subclasses], [])
    except:
        log.error("Could not get listeners:\n%s", traceback.format_exc())


if __name__ == "__main__":
    Daemon()

    for handler in logging.root.handlers:
        logging.root.removeHandler(handler)
    logging.root.addHandler(customlog.MultiprocessingStreamHandler())

    log = logging.getLogger(config.log_name)
    log.info("Starting %s...", config.app_name)

    track_queue = multiprocessing.Queue(1)
    log.info("Initializing read queue to hold %2.2f seconds of audio.",
             config.frontend_buffer)
    v2_queue = BufferedReadQueue(int(config.frontend_buffer / SECONDS_PER_FRAME))
    info_queue = multiprocessing.Queue()

    mixer = Mixer(iqueue=track_queue,
                  oqueues=(v2_queue.raw,),
                  infoqueue=info_queue)
    mixer.start()

    if stream:
        import brain
        Hotswap(track_queue.put, brain).start()
    Hotswap(InfoHandler.add, info, 'generate', info_queue).start()
    Hotswap(MonitorSocket.update,
            statistician, 'generate',
            get_listeners,
            mp3_queue=v2_queue).start()

    tornado.ioloop.PeriodicCallback(
        lambda: restart.check('restart.txt',
                              started_at_timestamp,
                              sum([len(x.listeners) for x in StreamHandler._StreamHandler__subclasses])),
        config.restart_timeout * 1000
    ).start()
    tornado.ioloop.PeriodicCallback(InfoHandler.clean, 5 * 1000).start()

    stream_routes = StreamHandler.init_streams([
        (r"/all.mp3", "All", v2_queue)
    ])

    application = tornado.web.Application(
        tornadio2.TornadioRouter(SocketConnection).apply_routes([
            # Static assets for local development
            (r"/(favicon.ico)", tornado.web.StaticFileHandler, {"path": "static/img/"}),
            (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": "static/"}),
            (r"/all.json", InfoHandler),
            (r"/monitor", MonitorHandler),
            (r"/", MainHandler)
        ] + stream_routes),
        socket_io_port=config.socket_port,
        enabled_protocols=['websocket', 'xhr-multipart', 'xhr-polling', 'jsonp-polling']
    )

    frame_sender = tornado.ioloop.PeriodicCallback(
        StreamHandler.stream_frames, SECONDS_PER_FRAME * 1000
    )
    frame_sender.start()

    application.listen(config.http_port)
    tornadio2.server.SocketServer(application)
