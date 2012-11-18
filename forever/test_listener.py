import socket
import time
import sys
from lame import frame_length


def listen(host, port, f="all.mp3"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    connect = "GET /%s HTTP/1.1\r\n\r\nHost: %s\r\n\r\n" % (f, host)
    print connect
    s.send(connect)

    at = None
    times = []

    start = None
    off = 0
    while True:
        start = s.recv(512)
        if "\xFF\xFB" in start:
            i = start.index("\xFF\xFB")
            off = len(start) - i - 4
            start = start[i:i + 4]
            break

    while True:
        if start:
            header = start
            start = None
        else:
            header = s.recv(4)
            off = 0
        if not len(header):
            break
        try:
            flen = frame_length(header)
            if (flen - 4 - off) < 0:
                raise ValueError()
        except:
            continue
        data = s.recv(flen - 4 - off)
        got = time.time()
        if not len(data):
            break
        if at:
            times.append(got - at)
            avg = ((1152 / 44100.0) / (sum(times) / len(times)))
            print "Frame (%d bytes, %2.5fs) received after %2.5fs\t(%2.2fx)\tAvg: %fx" % \
                    (len(data), 1152 / 44100.0, got - at,  (1152 / 44100.0) / (got - at), avg)
            times = times[:383]  # number of frames in the past 10 seconds
        at = got

if __name__ == "__main__":
    if len(sys.argv) > 2:
        listen(sys.argv[1], int(sys.argv[2]))
    else:
        listen("localhost", 8192)
