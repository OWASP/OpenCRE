from pprint import pprint
import logging
import os
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, NewType, Optional, Union

import semver
import yaml
from dacite import (
    Config,
    ForwardReferenceError,
    StrictUnionMatchError,
    UnexpectedDataError,
    from_dict,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# used for serialising and deserialising yaml OSIB documents

# default language is 'en'
default_lang = "en"

# Osib_id is an int or a string
Osib_id = NewType("Osib_id", str)

# Lang is a string, e.g. 'en', 'pt_BR')
Lang = NewType("Lang", str)


@dataclass
class _Osib_base:
    def to_dict(self) -> Dict[str, Any]:
        return asdict(
            self,
            dict_factory=lambda x: {
                k: v for (k, v) in x if v not in ["", {}, [], None]
            },
        )


@dataclass
class _Status(_Osib_base):
    """Status attributes decribing OSIB attributes and list items"""

    status: str = field(compare=False, default="")
    reviewed: Optional[int] = field(compare=False, default=None)
    change: str = field(compare=False, default="")


@dataclass
class _Link(_Status):
    """Basic attributes used by links-list items"""

    link: str = field(default="")  # osib id (=osib path to an object)
    type: Optional[str] = field(default=None)


@dataclass
class _Source(_Status):
    """Basic attributes used by i18n sources-directory items"""

    source: Optional[str] = field(default=None)  # url
    name: str = field(compare=False, default="")
    description: Optional[str] = field(compare=False, default=None)


@dataclass
class Node_attributes(_Status):
    """Attributes decribing an OSIB object"""

    source_id: Optional[str] = field(
        default=""
    )  # Unique id name by source, e.g. document
    links: List[_Link] = field(compare=False, default_factory=list)
    category: Optional[str] = field(compare=False, default=None)
    maturity: Optional[str] = field(compare=False, default=None)
    sources_i18n: Dict[Lang, Optional[_Source]] = field(
        compare=False, default_factory=dict
    )


@dataclass
class Osib_node(_Osib_base):

    """Object-Node for building the OSIB tree"""

    alias: Optional[Osib_id] = field(compare=False, default=None)
    attributes: Optional[Node_attributes] = field(compare=False, default=None)
    children: Optional[Dict[Union[int, str], "Osib_node"]] = field(
        compare=False, default=None
    )


@dataclass
class Osib_tree(Osib_node):
    """Root-Object for building the OSIB tree"""

    doctype: str = field(compare=False, default="OSIB")
    schema: Optional[str] = field(
        compare=False, default=semver.VersionInfo.parse("0.0.0")
    )
    # Date, when the tree has been comiled as int: YYYYMMDD
    date: Optional[str] = field(compare=False, default=None)


def read_osib_yaml(yaml_file: str = "") -> List[Dict[str, Any]]:
    with open(yaml_file, "r") as fin:
        osib_yaml = yaml.safe_load_all(fin)
        return [y for y in osib_yaml]


def try_from_file(data: List[Dict[str, Any]] = []) -> List[Osib_tree]:
    result = []
    for dat in data:
        result.append(from_dict(data_class=Osib_tree, data=dat))
    return result
