import os
import sys
from liveyamlfile import LiveYamlFile


class APIKeys(LiveYamlFile):
    pass

# This is a dirty, dirty hack, but lets you just do:
#   import apikeys
# and have access to an instantiated apikeys object.
sys.modules[__name__] = APIKeys(os.path.join(*(os.path.dirname(__file__).split(os.sep)[:-1] + ['api_keys.yml'])))
