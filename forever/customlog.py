__author__ = 'psobot'

import os
import logging
import multiprocessing
import threading
import sys
import traceback
import config
from logging.handlers import RotatingFileHandler

#
# _srcfile is used when walking the stack to check when we've got the first
# caller stack frame.
#

if hasattr(sys, 'frozen'):  # support for py2exe
    _srcfile = "logging%s__init__%s" % (os.sep, __file__[-4:])
elif __file__[-4:].lower() in ['.pyc', '.pyo']:
    _srcfile = __file__[:-4] + '.py'
else:
    _srcfile = __file__
_srcfile = os.path.normcase(_srcfile)


# next bit filched from 1.5.2's inspect.py
def currentframe():
    """Return the frame object for the caller's stack frame."""
    try:
        raise Exception
    except:
        return sys.exc_info()[2].tb_frame.f_back

if hasattr(sys, '_getframe'):
    currentframe = lambda: sys._getframe(3)
# done filching


class CustomLog(logging.Logger):
    """
    Basically a Logger instance with a built-in LoggingAdapter.
    Also multiprocess safe.
    """
    _g_handler = None

    def __init__(self, name):
        logging.Logger.__init__(self, name)
        self.extra = {'uid': ''}

        #   TODO: This appears to stop logging in production at some point.
        if not self._g_handler:
            self._g_handler = MultiprocessingLogHandler(os.path.abspath(config.log_file),
                                         "a", 1024 * 1024 * 512, 4)
            self._g_handler.setFormatter(logging.Formatter(config.log_format))
            self._g_handler.setLevel(logging.DEBUG)
            CustomLog._g_handler = self._g_handler
        self.addHandler(self._g_handler)

    def process(self, msg, kwargs):
        uid = ""
        if 'uid' in kwargs:
            uid = kwargs['uid']
            del kwargs['uid']
        return msg, dict({'extra': {"uid": uid}}.items() + kwargs.items())

    def debug(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        logging.Logger.debug(self, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        logging.Logger.info(self, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        logging.Logger.warning(self, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        logging.Logger.error(self, msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        kwargs["exc_info"] = 1
        logging.Logger.error(self, msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        logging.Logger.critical(self, msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        logging.Logger.log(self, level, msg, *args, **kwargs)

    def findCaller(self):
        """
        Find the stack frame of the caller so that we can note the source
        file name, line number and function name.

        As we're essentially re-calling Logger.log, we want to keep going
        farther up the callstack and reimplement this here in CustomLog.
        """
        f = currentframe()
        #On some versions of IronPython, currentframe() returns None if
        #IronPython isn't run with -X:Frames.
        if f is not None:
            f = f.f_back
        rv = "(unknown file)", 0, "(unknown function)"
        while hasattr(f, "f_code"):
            co = f.f_code
            filename = os.path.normcase(co.co_filename)
            if filename == _srcfile:
                f = f.f_back
                continue
            rv = (co.co_filename, f.f_lineno, co.co_name)
            break
        return rv


class MultiprocessingLogHandler(logging.Handler):
    """
        by zzzeek on SO:
        http://stackoverflow.com/questions/641420/how-should-i-log-while-using-multiprocessing-in-python
    """
    def __init__(self, *args, **kwargs):
        logging.Handler.__init__(self)
        self.lock = None

        if 'klass' in kwargs:
            klass = kwargs['klass']
            del kwargs['klass']
            self._handler = klass(*args, **kwargs)
        else:
            self._handler = RotatingFileHandler(*args, **kwargs)
        self.queue = multiprocessing.Queue(-1)

        t = threading.Thread(target=self.receive)
        t.daemon = True
        t.start()

    def setFormatter(self, fmt):
        logging.Handler.setFormatter(self, fmt)
        self._handler.setFormatter(fmt)

    def receive(self):
        while True:
            try:
                record = self.queue.get()
                self._handler.emit(record)
            except (KeyboardInterrupt, SystemExit):
                raise
            except EOFError:
                break
            except:
                traceback.print_exc(file=sys.stderr)

    def send(self, s):
        self.queue.put_nowait(s)

    def _format_record(self, record):
        # ensure that exc_info and args
        # have been stringified.  Removes any chance of
        # unpickleable things inside and possibly reduces
        # message size sent over the pipe
        if record.args:
            record.msg = record.msg % record.args
            record.args = None
        if record.exc_info:
            record.exc_info = None

        return record

    def emit(self, record):
        try:
            s = self._format_record(record)
            self.send(s)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

    def close(self):
        self._handler.close()
        logging.Handler.close(self)


class MultiprocessingStreamHandler(MultiprocessingLogHandler):
        def __init__(self):
            MultiprocessingLogHandler.__init__(self, sys.stdout,
                                               klass=logging.StreamHandler)
