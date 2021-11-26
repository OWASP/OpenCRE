from typing import Any, Dict, List, Union, NewType
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, field, asdict
from dacite import from_dict, Config, ForwardReferenceError, UnexpectedDataError, StrictUnionMatchError
import yaml
import warnings
import logging
import os

# used for serialising and deserialising yaml OSIB documents

debug               = 0                                             # debug level 0, 1 or 2
osib_yaml           = None
default_lang        = "en"                                          # default language is 'en'
Osib_id             = NewType('Osib_id', Union[int, str])           # Osib_id is an int or a string
Lang                = NewType('Lang'   , str)                       # Lang is a string, e.g. 'en', 'pt_BR')

log                 = logging.getLogger(__name__)                   # logging
if debug > 1:
  logging.basicConfig(level=logging.DEBUG)
elif debug > 0:
  logging.basicConfig(level=logging.INFO)

# define data classes
# internal (sub-)classes start with '_'
@dataclass
class _Status:
  '''Status attributes decribing OSIB attributes and list items'''
  status:       str                         = field(compare=False, default='none')
  reviewed:     int                         = field(compare=False, default=None)
  change:       str                         = field(compare=False, default='new')

@dataclass
class _Link(_Status):
  '''Basic attributes used by links-list items'''
  link:         str                         = field(               default=None)                # osib id (=osib path to an object)
  type:         str                         = field(               default=None)

@dataclass
class _Source(_Status):
  '''Basic attributes used by i18n sources-directory items'''
  source:       str                         = field(               default=None)                # url
  name:         str                         = field(compare=False, default=None)
  description:  str                         = field(compare=False, default=None)                # Dict[_String], optional

# external sequence classes
@dataclass
class Osib_attributes(_Status):
  '''Attributes decribing an OSIB object'''
  source_id:    Union[str, int]             = field(               default=None)                # Unique id name by source, e.g. document
  links:        List[_Link]                 = field(compare=False, default_factory=list)        # List[_Link]
  category:     str                         = field(compare=False, default=None)                # optional
  maturity:     str                         = field(compare=False, default=None)                # optional
  sources_i18n: Dict[Lang, _Source]         = field(compare=False, default_factory=dict)        # Dict[_Source]

@dataclass
class Osib_node():
  '''Object-Node for building the OSIB tree'''
#  path:       str                           = field(compare=False, default=None)               # optional TBD: path for humans to read the path
  alias:      Osib_id                       = field(compare=False, default=None)                # optional alias peer object; optional TBD: (path)
  attributes: Osib_attributes               = field(compare=False, default=None)
  children:   Dict[Osib_id, 'Osib_node']    = field(compare=False, default_factory=dict)        # Dict[Union[str, int], Osib_node]: Self Referencing is not supported, yet

@dataclass
class Osib_tree():
  '''Root-Object for building the OSIB tree'''
  doctype:    str                           = field(compare=False, default="OSIB")
  schema:     int                           = field(compare=False, default=None)                # Schema-Version: Major + 2 digits for minor version, e.g. 100 = V 1.00
  date:       int                           = field(compare=False, default=None)                # Date, when the tree has been comiled as int: YYYYMMDD
# define all fields of Osib_node as in Inheritance in data classes orders them at the beginning. But the order as defined here is preferred in exports
#  path:       str                 yaml_file          = field(compare=False, default=None)               # optional TBD: path for humans to read the path
  alias:      Osib_id                       = field(compare=False, default=None)                # optional alias peer object; optional TBD: (path)
  attributes: Osib_attributes               = field(compare=False, default=None)
  children:   Dict[Osib_id, Osib_node]      = field(compare=False, default_factory=dict)

  def to_dict(self) -> Dict[str, Any]:
    return asdict(self, dict_factory=lambda d: {k: v for (k, v) in d if v not in [None, {}, []]} )  # Skip keys with value None, {} or []

#### Subroutines ####
#
# read osib-YAML file
def read_osib_yaml(yaml_file=""):
  log = logging.getLogger(__name__)                                 # logging
  log.debug(f"osib_defs.py: read_osib_yaml(): read OSIB YAML file '{yaml_file}'.")
  with open(yaml_file, 'r') as fin:
    _osib_yaml = yaml.safe_load(fin)
  log.debug(f"osib_defs.py: OSIB YAML:\n{yaml.dump(_osib_yaml, sort_keys=False, indent=2, default_flow_style=False)}\n")
  return (_osib_yaml)

def try_from_dict(Class = None, dict = None, **args):
  default_path      = "osib"
  path              = args.get('path', default_path)                # default path is 'osib'
  result            = None
  logging.debug(f"osib_defs.py: try_from_dict ({path})")
  
  try:
    result = from_dict(Class , dict)
    logging.debug(f"osib_defs.py: try_from_dict ({path}): successful")
    return (result)

  except Exception as e:
    logging.debug(f"osib_defs.py: try_from_dict ({path}): error: {e}")
    message = e
    found   = ""
    if (not dict) or (dict == None):                                # if dict is None change it to an empty Osib Tree 
      dict = Osib_tree() 
      logging.warning(f"osib_defs.py: try_from_dict ({path}): undefined dict or with type None. Try to go on with an empty OSIB (sub-)tree")
    elif 'children' in dict:
      children = dict['children']
      if children and children != {}:
        for (key, value) in children.items():
          if (not value) or (value == None):                         # if value is None change it to an empty OSIB tree
            children[key] = {} # Osib_tree()
            result        = None
            logging.warning(f"osib_defs.py: try_from_dict ({path}.{key}): undefined child or with type None. Try to go on with an empty (sub-)OSIB tree")
          else:
            result=try_from_dict(Class, value, path=(path+'.'+str(key)) )
          if (not result) or (result==None):
            if found == "":
              found = "." + key
            else:
              found += "|" + key
        if found != "":
          logging.debug(f"osib_defs.py: try_from_dict ({path}{found}): found error {message}")
      else:
        logging.debug(f"osib_defs.py: try_from_dict ({path}): children dict is empty")
    else:
      logging.debug(f"osib_defs.py: try_from_dict ({path}): no further children")
    if found != "" and path == default_path:
      logging.warning(f"osib_defs.py: try_from_dict ({path}{found}): found errors in branches '{path}{found}': {message}. Try to get dict wihout check_types")
      return (from_dict(Class , dict, config=Config(check_types=False)) )
    logging.debug(f"osib_defs.py: try_from_dict ({path}{found}): return (None)")
    return (None)
  logging.warning(f"try_from_dict ({path}): Runtime Error: This line should be unreachable")
  return (result)

### Test ####
yaml_file = "include/osib_example.yml"
logger = logging.getLogger(__name__)
dict = read_osib_yaml(yaml_file)
osib = try_from_dict(Osib_tree, dict)
print (f"OSIB dict: ............. {dict}")
print (f"OSIB YAML dict:.........\n{yaml.dump(dict, sort_keys=False, indent=2, default_flow_style=False)}\n")
print (f"OSIB YAML Class:........\n{yaml.dump(osib.to_dict, sort_keys=False, indent=2, default_flow_style=False)}\n")
print (f"Class Osib_tree: ....... {osib}\n")
print (f"Dict osib.to_dict(): ... {osib.to_dict()}\n")
