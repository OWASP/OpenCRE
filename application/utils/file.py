from cre_logging import get_logger

logger = get_logger(__name__)

import os
from typing import Dict


def writeToDisk(file_title: str, cres_loc: str, file_content: str) -> Dict[str, str]:
    with open(os.path.join(cres_loc, file_title), "w+", encoding="utf8") as fp:
        fp.write(file_content)
    return {file_title: file_content}
