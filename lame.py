import subprocess
import threading
import time

BUF_LEN = 10  # seconds


class Lame(threading.Thread):
    """
        Live MP3 streamer. Currently only works for 16-bit, 44.1kHz stereo input.
    """
    input_wordlength = 16
    samplerate = 44100
    channels = 2
    bitrate = 256
    preset = "cbr %s" % bitrate
    real_time = True

    def __init__(self, data_notify_callback=None, ofile=None, oqueue=None):
        threading.Thread.__init__(self)

        self.lame = None
        self.buffered = 0
        self.oqueue = oqueue
        self.ofile = ofile
        self.data_notify_callback = data_notify_callback
        self.finished = False
        self.sent = False
        self.ready = threading.Semaphore()
        self.setDaemon(True)

    @property
    def pcm_datarate(self):
        return self.samplerate * self.channels * (self.input_wordlength / 8)

    def add_pcm(self, data):
        if self.lame.returncode is not None:
            return False
        try:
            while len(data):
                if self.buffered >= BUF_LEN:
                    self.ready.acquire()
                s = BUF_LEN * self.samplerate
                chunk = data[:s].tostring()
                data = data[s:]
                self.buffered += len(chunk) / (1.0 * self.pcm_datarate)
                self.lame.stdin.write(chunk)
            return True
        except IOError:
            # LAME could close the stream itself, or error
            return False

    #   TODO: Extend me to work for all bitwidths and samplerates
    def start(self, *args, **kwargs):
        call = ["lame"]
        call.append('-r')
        if self.input_wordlength != 16:
            call.extend(["--bitwidth", str(self.input_wordlength)])
        call.append("--preset")
        call.extend(self.preset.split())
        call.extend(["-", "-"])
        self.lame = subprocess.Popen(
            call,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        threading.Thread.start(self, *args, **kwargs)

    def ensure_is_alive(self):
        if self.finished:
            return False
        if self.is_alive():
            return True
        try:
            self.start()
            return True
        except Exception:
            return False

    def run(self, *args, **kwargs):
        while True:
            buf = self.lame.stdout.read(self.bitrate * 16)
            seconds_processed = len(buf) / (self.bitrate * 1024.0 / 8.0)
            self.buffered -= seconds_processed
            if self.buffered < BUF_LEN:
                self.ready.release()
            if len(buf):
                if self.oqueue:
                    self.oqueue.put(buf)
                if self.ofile:
                    self.ofile.write(buf)
                    self.ofile.flush()
                if self.data_notify_callback:
                    self.data_notify_callback(False)
                if self.real_time and self.sent:
                    time.sleep(seconds_processed)
                self.sent = True
            else:
                if self.data_notify_callback:
                    self.data_notify_callback(True)
                break
        self.lame.wait()

    def finish(self):
        """
            Closes input stream to LAME and waits for the last frame(s) to
            finish encoding. Returns LAME's return value code.
        """
        if self.lame:
            #   TODO: else raise an error maybe?
            self.lame.stdin.close()
            self.join()
            self.finished = True
            return self.lame.returncode
        return -1
