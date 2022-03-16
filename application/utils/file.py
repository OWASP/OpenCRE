import os
from typing import Dict


def writeToDisk(file_title: str, cres_loc: str, file_content: str) -> Dict[str, str]:
    # if "foo" in os.environ:
    #     print(file_title)
    #     input(1)
    #     os.environ.pop("foo")
    with open(os.path.join(cres_loc, file_title), "w+", encoding="utf8") as fp:
        fp.write(file_content)
    return {file_title: file_content}
