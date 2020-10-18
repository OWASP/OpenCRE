# make spreadsheets a frontend for the cre api
# export from spreadsheet to yaml
# yaml to github as a pull request
# import from rest api to spreadsheet

# given: a spreadsheet url
#   export to yaml
#   pull latest yaml from github
#   git merge
#   push to merge branch


# Qs:
# * do i have fs access with a spreadsheet app?
# * can i run git commands?
# * how do we make users setup a github account? maybe get them to create a GH api token?
# if i provide a GO/pex binary
#   can i compile for mac and windows?
#   is there a github client for go?
#   spreadsheets?

# A:
# i can sync s3 and google sheets
# i miss on merging
# i miss on who did what
#

import gspread
import yaml
import tempfile
import jsonschema
import json
import os.path
import logging
from git import Repo, Git
from pprint import pprint
from datetime import datetime

# todo: generate schema from existing yaml, validate against schema  -- done
# commit, issue pull request
# migrate gspread to work as a bot as well as oauth
# sync to spreadsheet (different script runs from master)
# make github action    https://www.jeffgeerling.com/blog/2020/running-github-actions-workflow-on-schedule-and-other-events

CRE_LINK_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "CRE-ID-lookup-from-taxonomy-table": {"type": "string"},
            "CS": {"type": "string"},
            # type string handles the edge-case of empty cell
            "CWE": {"type": ["number", "string"]},
            "Description": {"type": "string"},
            "Development guide (does not exist for SessionManagement)": {"type": "string"},
            "ID-taxonomy-lookup-from-ASVS-mapping": {"type": "string"},
            "Item": {"type": "string"},
            "Name": {"type": "string"},
            "OPC": {"type": "string"},
            "Top10 (lookup)": {"type": "string"},
            "WSTG": {"type": "string"},
        },
        "required": ["CRE-ID-lookup-from-taxonomy-table", "Description"]
    }
}
logging.basicConfig()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def readSpreadsheet(url: str, cres_loc: str):
    """given remote google spreadsheet url,
     reads each workbook into a yaml file in the local fs"""
    gc = gspread.oauth()
    sh = gc.open_by_url(url)
    logger.info("successfully opened spreadsheet %s" % url)
    for wsh in sh.worksheets():
        if wsh.title[0].isdigit():
            logger.info(
                "handling worksheet %s  (remember, only numbered worksheets will be processed by convention)" % wsh.title)
            records = wsh.get_all_records()
            toyaml = yaml.safe_load(yaml.dump(records))
            try:
                validateYaml(yamldoc=toyaml, schema=CRE_LINK_schema)
                logger.info("Worksheet is valid, saving to disk")
                with open(os.path.join(cres_loc, wsh.title+".yaml"), "wb") as fp:
                    fp.write(yaml.dump(toyaml, encoding='utf-8'))
            except jsonschema.exceptions.ValidationError as ex:
                logger.error(wsh.title + " failed validation")
                logger.error(ex)


def validateYaml(yamldoc: str, schema: str):
    jsonschema.validate(instance=yamldoc, schema=schema)


def pushToGithub(cre_loc: str, apikey, pullRequestName):
    repo = Repo(os.path.join(os.path.dirname(
        os.path.realpath(__file__)), "../../"))
    g = Git()
    commit_msg = "cre_sync_%s" % (datetime.now().isoformat().replace(":","."))
    logger.info("Pushing new branch %d, make sure you review and merge the branch to master if you want these updates into the REST API")
    g.checkout("-b",commit_msg)
    g.add(cre_loc)
    g.commit("-m",commit_msg)
    repo.remotes.origin.push(commit_msg)

def writeSpreadsheet(local, url):
    pass


spreadsheet_url = "https://docs.google.com/spreadsheets/d/1ACwnuvIwI6Lu3AikNUEeoc4wKoYd9wZ1eL4EtBP50kk/edit#gid=1618195737"
cre_loc = os.path.join(os.path.dirname(
    os.path.realpath(__file__)), "../../cres")
readSpreadsheet(spreadsheet_url, cres_loc=cre_loc)
pushToGithub(cre_loc, "", "")
