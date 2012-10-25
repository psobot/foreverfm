import colors
import cStringIO


class Metadata(object):
    client = None

    def __init__(self, obj):
        if hasattr(obj, 'obj'):
            self.obj = obj.obj
        else:
            self.obj = obj

    def __getattr__(self, name):
        if name in self.obj:
            return self.obj.get(name)
        raise AttributeError

    def fields(self):
        return self.obj

    def keys(self):
        return self.obj.keys()

    def find_color(self):
        if 'artwork_url' in self.obj:
            art = self.obj['artwork_url']
        else:
            art = self.obj['user']['avatar_url']
        fobj = cStringIO.StringIO(self.client.get(art).raw_data)
        return colors.colorz(fobj, 1)
