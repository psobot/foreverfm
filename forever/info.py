import base64
import logging
import threading
import scwaveform
from metadata import Metadata

log = logging.getLogger(__name__)


class Processor(threading.Thread):
    def __init__(self, info_queue, callback):
        threading.Thread.__init__(self)
        self.daemon = True
        self.info_queue = info_queue
        self.callback = callback

    def run(self):
        """
        Listen to streams of info from the remixer process and generate proper
        metadata about it. I.e.: Waveform images, colours, and the frontend data.

        TODO: Make this stream-agnostic (ideally, move info parsing into each stream.)
        """
        while True:
            action = self.info_queue.get()
            if len(action['tracks']) == 2:
                m1 = Metadata(action['tracks'][0]['metadata'])
                s1 = action['tracks'][0]['start']
                e1 = action['tracks'][0]['end']

                m2 = Metadata(action['tracks'][1]['metadata'])
                s2 = action['tracks'][1]['start']
                e2 = action['tracks'][1]['end']

                log.info("Processing metadata for %s -> %s, (%2.2fs %2.2fs) -> (%2.2fs, %2.2fs).",
                            m1.title, m2.title, s1, s2, e1, e2)

                a = scwaveform.generate([s1, s2], [e1, e2],
                                        [m1.color, m2.color],
                                        [m1.waveform_url, m2.waveform_url],
                                        [m1.duration, m2.duration],
                                        action['duration'])
            else:
                for track in action['tracks']:
                    metadata = Metadata(track['metadata'])
                    start = track['start']
                    end = track['end']

                    log.info("Processing metadata for %s, %2.2fs -> %2.2fs.",
                                metadata.title, start, end)
                    a = scwaveform.generate(start, end, metadata.color,
                                            metadata.waveform_url,
                                            metadata.duration,
                                            action['duration'])
            action['waveform'] = "data:image/png;base64,%s" % \
                                base64.encodestring(a)
            action['width'] = int(action['duration'] * scwaveform.DEFAULT_SPEED)
            self.callback(action)
