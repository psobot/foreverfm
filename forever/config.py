import os
import sys
from liveyamlfile import LiveYamlFile


class ConfigFile(LiveYamlFile):
    pass

# This is a dirty, dirty hack, but lets you just do:
#   import config
# and have access to an instantiated config object.
sys.modules[__name__] = ConfigFile(os.path.join(*(os.path.dirname(__file__).split(os.sep)[:-1] + ['config.yml'])))
