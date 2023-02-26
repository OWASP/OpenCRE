import copy
import os
import tempfile
import unittest
from collections import namedtuple
from dataclasses import asdict
from pprint import pprint
from unittest.mock import Mock, patch

import dacite
from application.database import db
from application.defs import cre_defs as defs
from application.utils.external_project_parsers import misc_tools_parser
from dacite import Config, from_dict


class TestMiscToolsParser(unittest.TestCase):
    @patch("application.database.db.dbCREfromCRE")
    @patch("application.database.db.Node_collection.get_CREs")
    @patch("application.database.db.Node_collection.add_link")
    @patch("application.database.db.Node_collection.add_node")
    @patch("application.utils.git.clone")
    def test_document_todict(
        self,
        mocked_clone,
        mocked_add_node,
        mocked_add_link,
        mocked_get_cres,
        mocked_dbCREfromCRE,
    ) -> None:
        Repo = namedtuple("Repo", ["working_dir", "url"])
        repo = Repo(working_dir=tempfile.mkdtemp(), url="")

        cre = defs.CRE(id="223-780", name="test")
        dbcre = db.CRE(external_id=cre.id, name=cre.name)

        expected = defs.Tool(
            name="OWASP WrongSecrets",
            doctype=defs.Credoctypes.Tool,
            description="With this app, we have packed various ways of how to not store your secrets. These can help you to realize whether your secret management is ok. The challenge is to find all the different secrets by means of various tools and techniques. Can you solve all the 14 challenges?) -->",
            tags=["secrets", "training"],
            hyperlink="https://example.com/foo/bar/project",
            tooltype=defs.ToolTypes.Training,
        )
        tags = [expected.tooltype.value]
        tags.extend(expected.tags)
        dbnode = db.Node(
            name=expected.name,
            ntype=expected.doctype.value,
            description=expected.description,
            tags=",".join(tags),
            link=expected.hyperlink,
            section=expected.section,
            ruleID=expected.ruleID,
        )

        mocked_clone.return_value = repo
        mocked_get_cres.return_value = [cre]
        mocked_add_node.return_value = dbnode
        mocked_dbCREfromCRE.return_value = dbcre

        readme_content = """<!-- CRE Link: [223-780](https://www.opencre.org/cre/223-780?register=true&type=tool&tool_type=training&tags=secrets,training&description=With%20this%20app%2C%20we%20have%20packed%20various%20ways%20of%20how%20to%20not%20store%20your%20secrets.%20These%20can%20help%20you%20to%20realize%20whether%20your%20secret%20management%20is%20ok.%20The%20challenge%20is%20to%20find%20all%20the%20different%20secrets%20by%20means%20of%20various%20tools%20and%20techniques.%20Can%20you%20solve%20all%20the%2014%20challenges%3F) -->
# OWASP WrongSecrets [![Tweet](https://img.shields.io/twitter/url/http/shields.io.svg?style=social)](https://twitter.com/intent/tweet?text=Want%20to%20dive%20into%20secrets%20management%20and%20do%20some%20hunting?%20try%20this&url=https://github.com/commjoen/wrongsecrets&hashtags=secretsmanagement,secrets,hunting,p0wnableapp,OWASP,WrongSecrets)
"""
        with open(os.path.join(repo.working_dir, "README.md"), "w") as rdm:
            rdm.write(readme_content)

        collection = db.Node_collection()
        misc_tools_parser.parse_tool(
            "https://example.com/foo/bar/project.git", collection
        )

        self.maxDiff = None
        mocked_get_cres.assert_called_with(external_id=cre.id)
        mocked_add_node.assert_called_with(node=expected)
        mocked_add_link.assert_called_with(
            cre=dbcre,
            node=dbnode,
            type=defs.LinkTypes.LinkedTo,
        )
