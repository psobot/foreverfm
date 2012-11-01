"""
echonest.audio monkeypatches
"""
import cStringIO
import numpy
import wave
import struct
import time
import os
import hashlib
import sys
import logging
import subprocess
import uuid
import gc
import weakref
from exceptionthread import ExceptionThread
from monkeypatch import monkeypatch_class

#   Sadly, we need to import * - this is a monkeypatch!
from echonest.audio import AudioAnalysis, AudioData, LocalAudioFile, AudioQuantumList
from echonest.support.ffmpeg import ffmpeg

FFMPEG_ERROR_TIMEOUT = 0.2


class AudioData(AudioData):
    __metaclass__ = monkeypatch_class

    def __init__(self,
                filename=None,
                ndarray = None,
                shape=None,
                sampleRate=None,
                numChannels=None,
                defer=False,
                verbose=True,
                filedata=None,
                rawfiletype='wav',
                uid=None,
                pcmFormat=numpy.int16):
        self.verbose = verbose
        if (filename is not None) and (ndarray is None):
            if sampleRate is None or numChannels is None:
                # force sampleRate and numChannels to 44100 hz, 2
                sampleRate, numChannels = 44100, 2
        self.filename = filename
        self.filedata = filedata
        self.rawfiletype = rawfiletype  #is this used?
        self.type = rawfiletype
        self.defer = defer
        self.sampleRate = sampleRate
        self.numChannels = numChannels
        self.convertedfile = None
        self.endindex = 0
        self.uid = uid
        if shape is None and isinstance(ndarray, numpy.ndarray) and not self.defer:
            self.data = numpy.zeros(ndarray.shape, dtype=numpy.int16)
        elif shape is not None and not self.defer:
            self.data = numpy.zeros(shape, dtype=numpy.int16)
        elif not self.defer and self.filename:
            self.data = None
            self.load(pcmFormat=pcmFormat)
        elif not self.defer and filedata:
            self.data = None
            self.load(filedata, pcmFormat=pcmFormat)
        else:
            self.data = None
        if ndarray is not None and self.data is not None:
            self.endindex = len(ndarray)
            self.data[0:self.endindex] = ndarray
        self.offset = 0
        self.read_destructively = True

    def load(self, file_to_read=None, pcmFormat=numpy.int16):
        if isinstance(self.data, numpy.ndarray):
            return

        if not file_to_read:
            if self.filename \
                and self.filename.lower().endswith(".wav") \
                and (self.sampleRate, self.numChannels) == (44100, 2):
                file_to_read = self.filename
            elif self.filedata \
                and self.type == 'wav' \
                and (self.sampleRate, self.numChannels) == (44100, 2):
                file_to_read = self.filedata
            elif self.convertedfile:
                file_to_read = self.convertedfile
            else:
                self.numChannels = 2
                self.sampleRate = 44100
                ndarray = ffmpeg(
                    (self.filename if self.filename else self.filedata),
                    numChannels=self.numChannels,
                    sampleRate=self.sampleRate,
                    verbose=self.verbose,
                    uid=self.uid,
                    format=self.type
                )
        else:
            file_to_read.seek(0)
            self.numChannels = 2
            self.sampleRate = 44100
            w = wave.open(file_to_read, 'r')
            numFrames = w.getnframes()
            self.numChannels = w.getnchannels()
            self.sampleRate = w.getframerate()
            raw = w.readframes(numFrames)
            data = numpy.frombuffer(raw, dtype="<h", count=len(raw) / 2)
            ndarray = numpy.array(data, dtype=pcmFormat)
            if self.numChannels > 1:
                ndarray.resize((numFrames, self.numChannels))
            w.close()

        #   If the file actually has a different sampleRate or numChannels,
        #   this is where we find out. FFMPEG detects and encodes the output
        #   stream appropriately.
        self.data = numpy.zeros((0,) if self.numChannels == 1
                                else (0, self.numChannels),
                                dtype=pcmFormat)
        self.endindex = 0
        if ndarray is not None:
            self.endindex = len(ndarray)
            self.data = ndarray

    def encode_to_stringio(self):
        fid = cStringIO.StringIO()
        # Based on Scipy svn
        # http://projects.scipy.org/pipermail/scipy-svn/2007-August/001189.html
        fid.write('RIFF')
        fid.write(struct.pack('<i', 0))  # write a 0 for length now, we'll go back and add it later
        fid.write('WAVE')
        # fmt chunk
        fid.write('fmt ')
        if self.data.ndim == 1:
            noc = 1
        else:
            noc = self.data.shape[1]
        bits = self.data.dtype.itemsize * 8
        sbytes = self.sampleRate * (bits / 8) * noc
        ba = noc * (bits / 8)
        fid.write(struct.pack('<ihHiiHH', 16, 1, noc, self.sampleRate, sbytes, ba, bits))
        # data chunk
        fid.write('data')
        fid.write(struct.pack('<i', self.data.nbytes))
        fid.write(self.data.tostring())
        # Determine file size and place it in correct
        # position at start of the file.
        size = fid.tell()
        fid.seek(4)
        fid.write(struct.pack('<i', size - 8))
        fid.seek(0)
        return fid

    def encode_to_string(self):
        return self.encode_to_stringio().getvalue()

    def encode(self, filename=None, mp3=None):
        if mp3:
            raise NotImplementedError("Static MP3 encoding is not yet implemented.")

        fid = open(filename, 'w')
        fid.write(self.encode_to_stringio().read())
        fid.close()

        return filename

    def convert_to_stereo(self):
        if self.numChannels < 2:
            self.data = self.data.flatten().tolist()
            self.data = numpy.array((self.data, self.data)).swapaxes(0, 1)
            self.numChannels = 2
        return self

    def play(self):
        if not self.data.dtype == numpy.int16:
            raise ValueError("Datatype is not 16-bit integers - this would blow off your ears!")
        #vlc_player_path = "/Applications/VLC.app/Contents/MacOS/VLC"
        null = open(os.devnull, 'w')
        try:
            cmd = ['play', '-t', 's16', '-c', str(self.numChannels),
                                     '-r', str(self.sampleRate), '-q', '-']
            print " ".join(cmd)
            proc = subprocess.Popen(cmd,
                                    stdin=subprocess.PIPE)
                                    #stdout=null, stderr=null)
            out, err = proc.communicate(self.data.tostring())
        except KeyboardInterrupt:
            pass
        """
        except:
            if os.path.exists(vlc_player_path):
                proc = subprocess.Popen(
                        [vlc_player_path, '-', 'vlc://quit', '-Idummy', '--quiet'],
                        stdin=subprocess.PIPE#,
                        #stdout=null,
                        #stderr=null
                )
                proc.communicate(self.encode_to_string())
                """
        null.close()

    def __getitem__(self, index):
        """
        Fetches a frame or slice. Returns an individual frame (if the index
        is a time offset float or an integer sample number) or a slice if
        the index is an `AudioQuantum` (or quacks like one).
        """
        if not isinstance(self.data, numpy.ndarray) and self.defer:
            self.load()
        if isinstance(index, float):
            index = int(index * self.sampleRate)
        elif hasattr(index, "start") and hasattr(index, "duration"):
            index =  slice(float(index.start), index.start + index.duration)

        if isinstance(index, slice):
            if (hasattr(index.start, "start") and
                hasattr(index.stop, "duration") and
                hasattr(index.stop, "start")) :
                index = slice(index.start.start, index.stop.start + index.stop.duration)

        if isinstance(index, slice):
            return self.getslice(index)
        else:
            return self.getsample(index)

    def getslice(self, index):
        "Help `__getitem__` return a new AudioData for a given slice"
        if not isinstance(self.data, numpy.ndarray) and self.defer:
            self.load()
        if isinstance(index.start, float):
            index = slice(int(index.start * self.sampleRate) - self.offset,
                            int(index.stop * self.sampleRate) - self.offset, index.step)
        else:
            index = slice(index.start - self.offset, index.stop - self.offset)
        a = AudioData(None, self.data[index], sampleRate=self.sampleRate,
                            numChannels=self.numChannels, defer=False)
        if self.read_destructively:
            self.remove_upto(index.start)
        return a

    def remove_upto(self, sample):
        if isinstance(sample, float):
            sample = int(sample * self.sampleRate)
        if sample:
            self.data = numpy.delete(self.data, slice(0, sample), 0)
            self.offset += sample
            gc.collect()


class LocalAudioFile(LocalAudioFile):
    """
    The basic do-everything class for remixing. Acts as an `AudioData`
    object, but with an added `analysis` selector which is an
    `AudioAnalysis` object. It conditianally uploads the file
    it was initialized with. If the file is already known to the
    Analyze API, then it does not bother uploading the file.
    """
    __metaclass__ = monkeypatch_class

    def __init__(self, data, kind="mp3", uid=None, verbose=False):
        if not uid:
            uid = str(uuid.uuid4()).replace('-', '')

        #   Initializing the audio file could be slow. Let's do this in parallel.
        AudioData.__init__(self, filedata=data, rawfiletype=type, verbose=verbose, defer=True, uid=uid)
        loading = ExceptionThread(target=self.load)
        loading.start()

        start = time.time()
        data.seek(0)
        track_md5 = hashlib.md5(data.read()).hexdigest()
        data.seek(0)

        if verbose:
            print >> sys.stderr, "Computed MD5 of file is " + track_md5

        logging.getLogger(__name__).info("Fetching analysis...")
        try:
            if verbose:
                print >> sys.stderr, "Probing for existing analysis"
            loading.join(FFMPEG_ERROR_TIMEOUT)
            tempanalysis = AudioAnalysis(str(track_md5))
        except Exception:
            if verbose:
                print >> sys.stderr, "Analysis not found. Uploading..."
            #   Let's fail faster - check and see if FFMPEG has errored yet, before asking EN
            loading.join(FFMPEG_ERROR_TIMEOUT)
            tempanalysis = AudioAnalysis(data, kind)

        logging.getLogger(__name__).info("Fetched analysis in %ss",
                                         (time.time() - start))
        loading.join()
        if self.data is None:
            raise AssertionError("LocalAudioFile has uninitialized audio data!")
        self.analysis = tempanalysis
        self.analysis.source = weakref.ref(self)


class AudioQuantumList(AudioQuantumList):
    __metaclass__ = monkeypatch_class

    @staticmethod
    def init_audio_data(source, num_samples):
        """
        Convenience function for rendering: return a pre-allocated, zeroed
        `AudioData`. Patched to return a 16-bit, rather than 32-bit.
        """
        if source.numChannels > 1:
            newchans = source.numChannels
            newshape = (num_samples, newchans)
        else:
            newchans = 1
            newshape = (num_samples,)
        return AudioData(shape=newshape, sampleRate=source.sampleRate,
                            numChannels=newchans, defer=False)

    def render(self, start=0.0, to_audio=None, with_source=None):
        if len(self) < 1:
            return
        if not to_audio:
            dur = 0
            tempsource = self.source or list.__getitem__(self, 0).source
            for aq in list.__iter__(self):
                dur += int(aq.duration * tempsource.sampleRate)
            to_audio = self.init_audio_data(tempsource, dur)
        if not hasattr(with_source, 'data'):
            for tsource in self.sources():
                this_start = start
                for aq in list.__iter__(self):
                    aq.render(start=this_start, to_audio=to_audio, with_source=tsource)
                    this_start += aq.duration
            return to_audio
        else:
            if with_source not in self.sources():
                return
            for aq in list.__iter__(self):
                aq.render(start=start, to_audio=to_audio, with_source=with_source)
                start += aq.duration
