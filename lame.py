import subprocess
import threading
import time
import traceback
from Queue import Queue

"""
Some important LAME facts used below:
    Each MP3 frame is identifiable by a header.
    This header has, essentially:
        "Frame Sync"            11 1's (i.e.: 0xFF + 3 bits)
        "Mpeg Audio Version ID" should be 0b11 for MPEG V1, 0b10 for MPEG V2
        "Layer Description"     should be 0b11
        "Protection Bit"        set to 1 by Lame, not protected
        "Bitrate index"         0000 -> free
                                0001 -> 32 kbps
                                0010 -> 40 kbps
                                0011 -> 48 kbps
                                0100 -> 56 kbps
                                0101 -> 64 kbps
                                0110 -> 80 kbps
                                0111 -> 96 kbps
                                1000 -> 112 kbps
                                1001 -> 128 kbps
                                1010 -> 160 kbps
                                1011 -> 192 kbps
                                1100 -> 224 kbps
                                1101 -> 256 kbps
                                1110 -> 320 kbps
                                1111 -> invalid

    Following the header, there are always 1152 samples of audio data.
    At our constant sampling frequency of 44100, this means each frame
    contains exactly .026122449 seconds of audio.
"""

BITRATE_TABLE = [
    0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, None
]
SAMPLERATE_TABLE = [
    44100, 48000, 32000, None
]
DEBUG_PRINT = True


class Lame(threading.Thread):
    """
        Live MP3 streamer. Currently only works for 16-bit, 44.1kHz stereo input.
    """
    safety_buffer = 30  # seconds
    input_wordlength = 16
    samplerate = 44100
    channels = 2
    preset = "-V2"
    real_time = False
    in_chunk_size = samplerate * channels * (input_wordlength / 8)
    chunk_size = 32768
    frame_interval = 8  # frames at a time that we send to the user
    data = None

    def __init__(self, data_notify_callback=None, ofile=None, oqueue=None):
        threading.Thread.__init__(self)

        self.lame = None
        self.buffered = 0
        self.mp3_output = 0
        self.pcm_input = 0
        self.mp3_bytes = 0
        self.next_starting_index = 0
        self.oqueue = oqueue
        self.ofile = ofile
        self.data_notify_callback = data_notify_callback
        self.finished = False
        self.sent = False
        self.ready = threading.Semaphore()
        self.encode = threading.Semaphore()
        self.setDaemon(True)
        self.tail_buf = ""

        self.__write_queue = Queue()
        self.__write_thread = threading.Thread(target=self.__lame_write)
        self.__write_thread.setDaemon(True)
        self.__write_thread.start()

        self.__testfile = open("testfile.pcm", 'w')

    @property
    def pcm_datarate(self):
        return self.samplerate * self.channels * (self.input_wordlength / 8)

    def add_pcm(self, data):
        if self.lame.returncode is not None:
            return False
        try:
            chunk = data.tostring()
            del data
            self.encode.acquire()
            self.__write_queue.put(chunk)
            if DEBUG_PRINT:
                print "Written PCM in!"
            if self.buffered >= self.safety_buffer:
                if DEBUG_PRINT:
                    print "ACQUIRING READY LOCK IN ADD_PCM"
                self.ready.acquire()
            if DEBUG_PRINT:
                print "DONE ADD PCM"
            return True
        except IOError:
            if DEBUG_PRINT:
                print "IOError!"
            # LAME could close the stream itself, or error
            return False

    def __lame_write(self):
        while not self.finished:
            if DEBUG_PRINT:
                print "Waiting for data..."
            data = self.__write_queue.get()
            if data is None:
                break
            if DEBUG_PRINT:
                print "Got data!"
            while len(data):
                chunk = data[:self.in_chunk_size]
                data = data[self.in_chunk_size:]
                self.buffered += len(chunk) / 4
                self.pcm_input += len(chunk) / 4
                if DEBUG_PRINT:
                    print "Writing chunk len:", len(chunk)
                    print "buffered:", self.buffered
                self.lame.stdin.write(chunk)
                self.__testfile.write(chunk)
                if DEBUG_PRINT:
                    print "len:", len(chunk)
            self.encode.release()
            if DEBUG_PRINT:
                print "Done lame write of len:", len(chunk)
            del chunk

    def frame_length(self, frame):
        assert len(frame) >= 4
        bitrate = BITRATE_TABLE[ord(frame[2]) >> 4]
        sample_rate = SAMPLERATE_TABLE[(ord(frame[2]) & 0b00001100) >> 2]
        padding = (ord(frame[2]) & 0b00000010) >> 1
        if DEBUG_PRINT:
            print "\t", bitrate,
            print "kbps\t", sample_rate, "Hz",
            print "\tpadded?", padding, "\t",

        return int((1152.0 / sample_rate) * ((bitrate / 8) * 1000)) + padding

    def get_frames(self, n_frames):
        valid_frame_count = 0
        while valid_frame_count < n_frames:
            _buf = self.lame.stdout.read(max(1045, self.chunk_size))
            self.mp3_bytes += len(_buf)

            if not _buf:
                if self.tail_buf:
                    tb = self.tail_buf
                    self.tail_buf = ""
                    return tb, 1152.0 / 44100.0
                else:
                    return "", 0
            buf = self.tail_buf + _buf

            # Look for the first frame header
            if hasattr(self, 'next_starting_index'):
                s = self.next_starting_index
            else:
                s = buf.index("\xFF\xFB")
            if DEBUG_PRINT:
                print "Starting index:", s
            l = self.frame_length(buf[s:])
            if DEBUG_PRINT:
                print "Length of first frame:", l
            while s < len(buf) and (len(buf) - s) > 3:
                s += buf[s:].index("\xFF\xFB")
                print s
                if DEBUG_PRINT:
                    print "Header: %0X%0X%0X%0X" % tuple([ord(x) for x in buf[s:s + 4]]),
                    print "at %d" % (self.mp3_bytes + s),
                l = self.frame_length(buf[s:])
                if s + l > len(buf):
                    if DEBUG_PRINT:
                        print "next frame size exceeds grabbed buffer:", (l), len(buf) - s
                    self.next_starting_index = max(0, (s + l) - len(buf))
                    break
                else:
                    self.next_starting_index = 0
                frame = buf[s:s + l]
                s += l

                if DEBUG_PRINT:
                    print "Got frame:\t", len(frame), "bytes",
                    print
                valid_frame_count += 1
            self.tail_buf = buf[s:]
            print "len of tail buf:", len(self.tail_buf)
            if DEBUG_PRINT:
                print "Set next starting index to", self.next_starting_index
        return _buf, (valid_frame_count * 1152)

    #   TODO: Extend me to work for all bitwidths and samplerates
    def start(self, *args, **kwargs):
        call = ["lame"]
        call.append('-r')
        if self.input_wordlength != 16:
            call.extend(["--bitwidth", str(self.input_wordlength)])
        call.extend(self.preset.split())
        call.extend(["-", "-"])
        if DEBUG_PRINT:
            print " ".join(call)
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
        try:
            while True:
                buf, samples = self.get_frames(self.frame_interval)
                self.buffered -= samples
                self.mp3_output += samples
                if self.buffered < 0:
                    print "OHNOES::::::::: Buffered length is less than 0! Written", self.pcm_input, "bytes of PCM, read", self.mp3_output, "samples of MP3"
                    print "OHNOES::::::::: Got", (self.mp3_output - self.pcm_input), "extra samples!"
                    assert False
                    self.buffered = 0
                if DEBUG_PRINT:
                    print self.buffered, "samples still buffered in LAME"
                    print self.pcm_input, "samples input"
                    print self.mp3_output, "samples output"
                if self.buffered < self.safety_buffer:
                    if DEBUG_PRINT:
                        print "RELEASING READY LOCK AT", self.buffered
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
                        time.sleep(samples / 44100.0)
                    self.sent = True
                else:
                    if self.data_notify_callback:
                        self.data_notify_callback(True)
                    break
            self.lame.wait()
        except:
            if DEBUG_PRINT:
                print "EXCEPTED!"
            traceback.print_exc()
            self.finish()
            raise

    def finish(self):
        """
            Closes input stream to LAME and waits for the last frame(s) to
            finish encoding. Returns LAME's return value code.
        """
        if self.lame:
            #   TODO: else raise an error maybe?
            self.__write_queue.put(None)
            self.encode.acquire()
            self.lame.stdin.close()
            self.join()
            self.finished = True
            return self.lame.returncode
        return -1

if __name__ == "__main__":
    import wave
    import numpy
    f = wave.open("test.wav")
    a = numpy.frombuffer(f.readframes(f.getnframes()), dtype=numpy.int16).reshape((-1, 2))

    for exp in xrange(13, 16):
        s = time.time()
        chunk_size = 2 ** exp
        print "Trying with chunk size: %d" % chunk_size
        encoder = Lame(ofile=open('testout.mp3', 'w'))
        encoder.chunk_size = chunk_size
        encoder.safety_buffer = 30
        encoder.start()
        encoder.add_pcm(a)
        encoder.finish()
        s = time.time() - s
        print "Time with buffer size %d: %fs" % (chunk_size, s)
        print "\tFed LAME", encoder.pcm_input, "samples of PCM data (", (encoder.pcm_input / float(encoder.samplerate)), "seconds)"
        print "\tGot back", encoder.mp3_output, "samples of MP3 data (", (encoder.mp3_output / float(encoder.samplerate)), "seconds)"
