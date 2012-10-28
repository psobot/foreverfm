import colors
import cStringIO

PIXELS_PER_SECOND = 1


class Metadata(object):
    client = None
    __color = None

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

    @property
    def color(self):
        if not self.__color:
            if 'artwork_url' in self.obj:
                art = self.obj['artwork_url']
            else:
                art = self.obj['user']['avatar_url']
            fobj = cStringIO.StringIO(self.client.get(art).raw_data)
            self.__color = colors.colorz(fobj, 1)[0]
        return self.__color
