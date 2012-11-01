import os
import subprocess
import sys
import inspect
import config as config


def get_calling_module():
    for frame in inspect.stack():
        mod = inspect.getmodule(frame[0])
        if mod is not sys.modules[__name__]:
            return mod
    return sys.modules[__name__]


class Daemon():
    """
    Dirty little class to daemonize a script.
    Uses Linux/Unix/OS X commands to do its dirty work.
    Works for daemonizing a Tornado server, while other
    pythonic ways of daemonizing a process fail.
    """
    def __init__(self, pidfile=None, module=True):
        self.pidfile = "%s.pid" % sys.argv[0] if not pidfile else pidfile
        self.module = module
        self.file = os.path.abspath(sys.argv[0])
        self.handleDaemon()

    def start(self):
        if os.path.exists('forever.pid'):
            print '%s is already running!' % config.app_name
            exit(1)
        print ("Starting %s..." % config.app_name),
        devnull = open(os.devnull, 'w')
        if not self.module:
            args = ['nohup', 'python', self.file]
        else:
            caller = get_calling_module()
            module_path = ".".join([caller.__package__,
                                    os.path.splitext(os.path.basename(caller.__file__))[0]])
            args = ['nohup', 'python', '-m', module_path]
        pid = subprocess.Popen(
              args,
              stdin=devnull,
              stdout=devnull,
              stderr=devnull
            ).pid
        print "done. (PID: %s)" % pid
        open(self.pidfile, 'w').write(str(pid))

    def stop(self):
        if not os.path.exists(self.pidfile):
            print '%s is not running!' % config.app_name
        else:
            print ("Stopping %s..." % config.app_name),
            subprocess.Popen(['kill', '-2', open(self.pidfile).read()])
            print "done."
            if os.path.exists(self.pidfile):
                os.remove(self.pidfile)

    def handleDaemon(self):
        # The main process should be stopped only with a SIGINT for graceful cleanup.
        # i.e.: kill -2 `wubmachine.pid` if you really need to do it manually.

        if len(sys.argv) == 2:
            if sys.argv[1] == "start":    #   fast and cheap
                self.start()
                exit(0)
            elif sys.argv[1] == "stop":
                self.stop()
                exit(0)
            elif sys.argv[1] == 'restart':
                self.stop()
                self.start()
                exit(0)
