"""
echonest.audio monkeypatches
"""
import cPickle
import cStringIO
import traceback
import errno
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

from exceptionthread import ExceptionThread
from monkeypatch import monkeypatch_class

#   Sadly, we need to import * - this is a monkeypatch!
from echonest.audio import *

FFMPEG_ERROR_TIMEOUT = 0.2

#######
#   Custom, in-memory FFMPEG decoders
#######


def ffmpeg_error_check(parsestring):
    """Looks for known errors in the ffmpeg output"""
    parse = parsestring.split('\n')
    error_cases = ["Unknown format",        # ffmpeg can't figure out format of input file
                   "error occur",           # an error occurred
                   "Could not open",        # user doesn't have permission to access file
                   "not found",             # could not find encoder for output file
                   "Invalid data found",    # could not find encoder for output file
                   "Could not find codec parameters"
    ]
    for num, line in enumerate(parse):
        if "command not found" in line:
            raise RuntimeError(ffmpeg_install_instructions)
        for error in error_cases:
            if error in line:
                report = "\n\t".join(parse[num:])
                raise RuntimeError("ffmpeg conversion error:\n\t" + report)


def ffmpeg(infile,
            bitRate=None,
            numChannels=None,
            sampleRate=None,
            verbose=True,
            uid=None,
            format=None,
            lastTry=False):
    """
    Executes ffmpeg through the shell to convert or read media files.
    This custom version does the conversion in-memory - no temp files involved. Quicker, too.
    """
    start = time.time()

    filename = None
    if type(infile) is str or type(infile) is unicode:
        filename = str(infile)

    command = "en-ffmpeg"
    if filename:
        command += " -i \"%s\"" % infile
    else:
        command += " -i pipe:0"
    if bitRate is not None:
        command += " -ab " + str(bitRate) + "k"
    if numChannels is not None:
        command += " -ac " + str(numChannels)
    if sampleRate is not None:
        command += " -ar " + str(sampleRate)
    command += " -f s16le -acodec pcm_s16le pipe:1"
    logging.getLogger(__name__).info("Calling ffmpeg: %s", command)

    (lin, mac, win) = get_os()
    p = subprocess.Popen(
        command,
        shell=True,
        stdin=(None if filename else subprocess.PIPE),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=(not win)
    )
    if filename:
        f, e = p.communicate()
    else:
        infile.seek(0)
        f, e = p.communicate(infile.read())
        infile.seek(0)

    if 'Could not find codec parameters' in e and format and not lastTry:
        logging.getLogger(__name__).warning("FFMPEG couldn't find codec parameters - writing to temp file.")
        fd, name = tempfile.mkstemp('.' + format)
        handle = os.fdopen(fd, 'w')
        infile.seek(0)
        handle.write(infile.read())
        handle.close()
        r = ffmpeg(name,
                   bitRate=bitRate,
                   numChannels=numChannels,
                   sampleRate=sampleRate,
                   verbose=verbose,
                   uid=uid,
                   format=format,
                   lastTry=True)
        logging.getLogger(__name__).info("Unlinking temp file at %s...", name)
        os.unlink(name)
        return r
    ffmpeg_error_check(e)
    mid = time.time()
    arr = numpy.frombuffer(f, dtype=numpy.int16).reshape((-1, 2))
    logging.getLogger(__name__).info("Decoded in %ss.", (mid - start))
    return arr


def ffmpeg_downconvert(infile, format=None, uid=None, lastTry=False):
    """
    Executes ffmpeg through the shell to convert or read media files.
    This custom version does the conversion in-memory - no temp files involved. Quicker, too.
    """
    start = time.time()

    filename = None
    if type(infile) is str or type(infile) is unicode:
        filename = str(infile)

    command = "en-ffmpeg"
    if filename:
        command += " -i \"%s\"" % infile
    else:
        command += " -i pipe:0"
    command += " -b 32k -f mp3 pipe:1"
    logging.getLogger(__name__).info("Calling ffmpeg: %s", command)

    (lin, mac, win) = get_os()
    p = subprocess.Popen(
        command,
        shell=True,
        stdin=(None if filename else subprocess.PIPE),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=(not win)
    )
    if filename:
        f, e = p.communicate()
    else:
        infile.seek(0)
        f, e = p.communicate(infile.read())
        infile.seek(0)

    if 'Could not find codec parameters' in e and format and not lastTry:
        logging.getLogger(__name__).warning("FFMPEG couldn't find codec parameters - writing to temp file.")
        fd, name = tempfile.mkstemp('.' + format)
        handle = os.fdopen(fd, 'w')
        infile.seek(0)
        handle.write(infile.read())
        handle.close()
        r = ffmpeg_downconvert(name, format=format, uid=uid, lastTry=True)
        logging.getLogger(__name__).info("Unlinking temp file at %s...", name)
        os.unlink(name)
        return r
    ffmpeg_error_check(e)

    io = cStringIO.StringIO(f)
    end = time.time()
    io.seek(0, os.SEEK_END)
    bytesize = io.tell()
    io.seek(0)
    logging.getLogger(__name__).info("Transcoded to 32kbps mp3 in %ss. Final size: %s bytes.",
                                     (end - start), bytesize)
    return io


#######
#   More efficient EN methods
#######
def getpieces(audioData, segs):
    """
    Collects audio samples for output.
    Returns a new `AudioData` where the new sample data is assembled
    from the input audioData according to the time offsets in each
    of the elements of the input segs (commonly an `AudioQuantumList`).

    :param audioData: an `AudioData` object
    :param segs: an iterable containing objects that may be accessed
        as slices or indices for an `AudioData`
    """
    #calculate length of new segment
    audioData.load()
    dur = 0
    for s in segs:
        dur += int(s.duration * audioData.sampleRate)
        # if I wanted to add some padding to the length, I'd do it here

    #determine shape of new array
    if len(audioData.data.shape) > 1:
        newshape = (dur, audioData.data.shape[1])
        newchans = audioData.data.shape[1]
    else:
        newshape = (dur,)
        newchans = 1

    #make accumulator segment
    newAD = AudioData(shape=newshape, sampleRate=audioData.sampleRate,
        numChannels=newchans, verbose=audioData.verbose)

    #concatenate segs to the new segment
    for s in segs:
        newAD.append(audioData[s])
        # audioData.unload()
    return newAD


#######
#   Patched, in-memory audio handlers
#######

class AudioAnalysis(AudioAnalysis):
    __metaclass__ = monkeypatch_class

    def __init__(self, initializer, filetype = None, lastTry = False):
        if type(initializer) is not str and not hasattr(initializer, 'read'):
            # Argument is invalid.
            raise TypeError("Argument 'initializer' must be a string \
                            representing either a filename, track ID, or MD5, or \
                            instead, a file object.")

        try:
            if type(initializer) is str:
                # see if path_or_identifier is a path or an ID
                if os.path.isfile(initializer):
                    # it's a filename
                    self.pyechonest_track = track.track_from_filename(initializer)
                else:
                    if initializer.startswith('music://') or \
                       (initializer.startswith('TR') and
                        len(initializer) == 18):
                        # it's an id
                        self.pyechonest_track = track.track_from_id(initializer)
                    elif len(initializer) == 32:
                        # it's an md5
                        self.pyechonest_track = track.track_from_md5(initializer)
            else:
                assert(filetype is not None)
                initializer.seek(0)
                try:
                    self.pyechonest_track = track.track_from_file(initializer, filetype)
                except (IOError, pyechonest.util.EchoNestAPIError) as e:
                    if lastTry:
                        raise

                    if (isinstance(e, IOError)
                        and (e.errno in [errno.EPIPE, errno.ECONNRESET]))\
                    or (isinstance(e, pyechonest.util.EchoNestAPIError)
                        and any([("Error %s" % x) in str(e) for x in [-1, 5, 6]])):
                        logging.getLogger(__name__).warning("Upload to EN failed - transcoding and reattempting.")
                        self.__init__(ffmpeg_downconvert(initializer, filetype), 'mp3', lastTry=True)
                        return
                    elif (isinstance(e, pyechonest.util.EchoNestAPIError)
                            and any([("Error %s" % x) in str(e) for x in [3]])):
                        logging.getLogger(__name__).warning("EN API limit hit. Waiting 10 seconds.")
                        time.sleep(10)
                        self.__init__(initializer, filetype, lastTry=False)
                        return
                    else:
                        logging.getLogger(__name__).warning("Got unhandlable EN exception. Raising:\n%s",
                                                            traceback.format_exc())
                        raise
        except Exception as e:
            if lastTry or type(initializer) is str:
                raise

            if "the track is still being analyzed" in str(e)\
            or "there was an error analyzing the track" in str(e):
                logging.getLogger(__name__).warning("Could not analyze track - truncating last byte and trying again.")
                try:
                    initializer.seek(-1, os.SEEK_END)
                    initializer.truncate()
                    initializer.seek(0)
                except IOError:
                    initializer.seek(-1, os.SEEK_END)
                    new_len = initializer.tell()
                    initializer.seek(0)
                    initializer = cStringIO.StringIO(initializer.read(new_len))
                self.__init__(initializer, filetype, lastTry=True)
                return
            else:
                logging.getLogger(__name__).warning("Got a further unhandlable EN exception. Raising:\n%s",
                                                    traceback.format_exc())
                raise

        if self.pyechonest_track is None:
            #   This is an EN-side error that will *not* be solved by repeated calls
            if type(initializer) is str:
                raise EchoNestRemixError('Could not find track %s' % initializer)
            else:
                raise EchoNestRemixError('Could not find analysis for track!')

        self.source = None

        self._bars = None
        self._beats = None
        self._tatums = None
        self._sections = None
        self._segments = None

        self.identifier = self.pyechonest_track.id
        self.metadata   = self.pyechonest_track.meta

        for attribute in ('time_signature', 'mode', 'tempo', 'key'):
            d = {'value': getattr(self.pyechonest_track, attribute),
                 'confidence': getattr(self.pyechonest_track, attribute + '_confidence')}
            setattr(self, attribute, d)

        for attribute in ('end_of_fade_in', 'start_of_fade_out', 'duration', 'loudness'):
            setattr(self, attribute, getattr(self.pyechonest_track, attribute))


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

    def __init__(self, data=None, type=None, uid=None, verbose=False):
        assert(data is not None)
        assert(type is not None)

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

        filepath = "cache/%s.pickle" % track_md5
        logging.getLogger(__name__).info("Fetching analysis...")
        try:
            if verbose:
                print >> sys.stderr, "Probing for existing local analysis"
            if os.path.isfile(filepath):
                tempanalysis = cPickle.load(open(filepath, 'r'))
            else:
                if verbose:
                    print >> sys.stderr, "Probing for existing analysis"
                loading.join(FFMPEG_ERROR_TIMEOUT)
                tempanalysis = AudioAnalysis(str(track_md5))
        except Exception:
            if verbose:
                print >> sys.stderr, "Analysis not found. Uploading..."
            #   Let's fail faster - check and see if FFMPEG has errored yet, before asking EN
            loading.join(FFMPEG_ERROR_TIMEOUT)
            tempanalysis = AudioAnalysis(data, type)

        if not os.path.isfile(filepath):
            cPickle.dump(tempanalysis, open(filepath, 'w'), 2)
        logging.getLogger(__name__).info("Fetched analysis in %ss",
                                         (time.time() - start))
        loading.join()
        if self.data is None:
            raise AssertionError("LocalAudioFile has uninitialized audio data!")
        self.analysis = tempanalysis
        self.analysis.source = self


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


def truncatemix(dataA, dataB, mix=0.5):
    """
    Mixes two "AudioData" objects. Assumes they have the same sample rate
    and number of channels.

    Mix takes a float 0-1 and determines the relative mix of two audios.
    i.e., mix=0.9 yields greater presence of dataA in the final mix.

    If dataB is longer than dataA, dataB is truncated to dataA's length.
    """
    newdata = AudioData(ndarray=dataA.data, sampleRate=dataA.sampleRate,
        numChannels=dataA.numChannels, verbose=False)
    newdata.data *= float(mix)
    if dataB.endindex > dataA.endindex:
        newdata.data[:] += dataB.data[:dataA.endindex] * (1 - float(mix))
    else:
        newdata.data[:dataB.endindex] += dataB.data[:] * (1 - float(mix))
    return newdata


def genFade(fadeLength, dimensions=1):
    fadeOut = numpy.linspace(1.0, 0.0, fadeLength) ** 2
    if dimensions == 2:
        return fadeOut[:, numpy.newaxis]
    return fadeOut


def fadeEdges(input, fadeLength=50):
    """
        Fade in/out the ends of an audioData to prevent clicks.
        Optional fadeLength argument is the number of samples to fade in/out.
    """
    if isinstance(input, AudioData):
        ad = input.data
    elif isinstance(input, numpy.ndarray):
        ad = input
    else:
        raise Exception("Cannot fade edges of unknown datatype.")
    fadeOut = genFade(min(fadeLength, len(ad)), ad.shape[1])
    ad[0:fadeLength] *= fadeOut[::-1]
    ad[-1 * fadeLength:] *= fadeOut
    return input


def normalize(audio):
    #   TODO: Ensure this will work on multiple datatypes.
    audio.data *= (32760.0 / numpy.max(numpy.abs(audio.data)))
    return audio
