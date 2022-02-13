# parse https://github.com/blabla1337/skf-flask/blob/main/skf/initial_data.py
# extract relevant data:
# * code <-- start here
# * recommendations
#
# insert into CRE
# Prereq:
# * clone their repo and set a github action to only keep relevant dirs (start with code, expand as needed)
# * parse the relevant dirs only and use this repo as the base
# * hyperlinks should link to skf demo
#

import os
import re
from typing import List

from application.database import db
from application.defs import cre_defs as defs
from application.utils import git
from isort import file


def skf_code_sample(
    name: str, description: str, tags: List[str], code_loc: str
) -> defs.Code:
    return defs.Code(
        name=f"Security Knowledge Framework Code Sample: {name}",
        description=description,
        tags=tags,
        hyperlink=code_loc,
    )


def parse_skf_code_samples(cache: db.Node_collection):
    """* clone target repo (skf repo)
        * for each code .md sample
            find which ASVS/MASVS section/subsection it links to
            find what's it's github or SKF website link
            add it as "code" in the db
    repo path is https://raw.githubusercontent.com/blabla1337/skf-flask/main/skf/markdown/code_examples/web/django-needs-reviewing/10-code_example--Anti_clickjacking_headers--.md
    """
    namer = r"#(?P<title>.+)\n-+"
    tagsr = r""
    coder = r"## Example:? ?(?P<code>.+)"
    content_root = "https://github.com/blabla1337/skf-flask.git"  # url to skf data
    code_path = "skf/markdown/code_examples/web/"
    skf_base = "https://demo.skf...."  # some path we can use as the base for hyperlinks

    repo = git.clone(content_root)
    from pprint import pprint

    for root, langs, files in os.walk(os.path.join(repo.working_dir, code_path)):
        name = None
        description = None
        code_loc = None
        for file in files:
            if not file.endswith(".md"):
                continue
            with open(os.path.join(root, file)) as mdf:
                name_raw = file.split("-")
                kb_id = name_raw[0].replace("_", " ")
                file_title = name_raw[3].replace("_", " ")

                mdtext = mdf.read()
                title = re.search(namer, mdtext, re.MULTILINE)
                if title:
                    name = title.group("title")

                lang_tag = os.path.dirname(os.path.join(root,file)).split("/")[-1]
                code_loc = content_root.replace(".git","/blob/main/") + os.path.join(code_path,lang_tag,file)
                desc = re.search(coder, mdtext, re.DOTALL)
                if desc:
                    description = desc.group("code")

                code = skf_code_sample(
                    name=name,
                    description=description,
                    tags=[f"language:{lang_tag}"],
                    code_loc=code_loc,
                )
                pprint(code.todict())
                # dbnode = cache.add_node(code)

            # TODO: find what ASVS or MASVS this links to and link it. seems the db table checklist_kb and the checklist_kb_id seems to correspond to asvs
            # category id for everything is 1?
            # https://github.com/blabla1337/skf-flask/blob/1f2c322c70c7fb1c1c4abd54abfc28c3aa8585aa/skf/db_tools.py#L118

            # SKF does it in this method https://github.com/blabla1337/skf-flask/blob/1f2c322c70c7fb1c1c4abd54abfc28c3aa8585aa/skf/db_tools.py#L68
