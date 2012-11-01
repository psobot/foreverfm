import os
import coffeescript
import scss as pyScss
import logging
import traceback
from timer import Timer

log = logging.getLogger(__name__)

#   Quick hacky way to figure out how much of the path we need to return.
#   Should be /{WEB_ROOT}/compiled_asset_files
WEB_ROOT = "static"

cachebust_on_passthrough = True


class AssetHandler(object):
    in_extensions = []
    out_extension = None

    in_directory = "assets"
    out_directory = "static/assets/"

    def __init__(self, filenames):
        self.filenames = filenames

    @classmethod
    def can_handle(self, filename):
        return any([filename.endswith(e) for e in self.in_extensions])

    def compile(self):
        return "\n".join([self.compile_one(f) for f in self.filenames])

    def compile_one(self, filename):
        return open(filename, 'r').read()

    def compile_and_save(self):
        if not self.has_been_compiled:
            with Timer() as t:
                compiled = self.compile()
                with open(self.dest_filename, 'w') as f:
                    f.write(compiled)
            log.info("Compiled asset in %2.2fms \"%s\" => \"%s\".", t.ms,
                     ", ".join(self.filenames), self.dest_filename)
        return self.path_for_web

    @property
    def has_been_compiled(self):
        return os.path.isfile(self.dest_filename)

    @property
    def path_for_web(self):
        comp = self.dest_filename.split(os.path.sep)
        return "/".join([''] + comp[comp.index(WEB_ROOT):])

    @property
    def dest_filename(self):
        tokens = []
        for filename in self.filenames:
            f = os.path.basename(filename)
            name, ext = os.path.splitext(f)
            tokens.append("%s-%d" % (name, os.stat(filename).st_mtime))
        newf = "%s.%s" % ("_".join(tokens),
                          self.out_extension if self.out_extension else ext[1:])
        if self.out_directory:
            return os.path.abspath(os.path.join(
                os.path.dirname(self.out_directory), newf
            ))
        else:
            return os.path.abspath(os.path.join(
                os.path.dirname(self.filenames[0]), newf
            ))


class __coffeescript(AssetHandler):
    in_extensions = ["coffee"]
    out_extension = "js"

    def compile_one(self, filename):
        return coffeescript.compile(open(filename, 'r').read())


class __scss(AssetHandler):
    in_extensions = ["scss"]  # sass not quite yet supported
    out_extension = "css"
    css = pyScss.Scss()

    def compile_one(self, filename):
        return self.css.compile(open(filename, 'r').read())

handlers = [__coffeescript, __scss]


def resolve(*_f):
    try:
        filenames = []
        for filename in _f:
            if not os.path.exists(filename):
                filenames.append(os.path.join(AssetHandler.in_directory, filename))
            else:
                filenames.append(filename)

        for handler in handlers:
            if all([handler.can_handle(filename) for filename in filenames]):
                return handler(filenames).compile_and_save()

        return AssetHandler(filenames).compile_and_save()
    except Exception:
        log.error("Asset compilation failed on file \"%s\":\n%s", filename,
                  traceback.format_exc())
        raise

compiled = resolve
