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
from git import Repo, Git
from pprint import pprint
from datetime import datetime

# todo: generate schema from existing yaml, validate against schema  -- done
# commit, issue pull request
# migrate gspread to work as a bot as well as oauth
# sync to spreadsheet (different script runs from master)
# use https://gitpython.readthedocs.io/en/stable/ to do the pull requests, skip github stuff for now
#

CRE_LINK_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "CRE-ID-lookup-from-taxonomy-table": {"type": "string"},
            "CS": {"type": "string"},
            "CWE": {"type": ["number","string"]}, # type string handles the edge-case of empty cell
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
 
def readSpreadsheet(url: str,cres_loc:str):
    """given remote google spreadsheet url,
     reads each workbook into a yaml file in the local fs"""
    gc = gspread.oauth()
    sh = gc.open_by_url(url)
    for wsh in sh.worksheets():
        print(wsh.title)
        if wsh.title[0].isdigit():
            records = wsh.get_all_records()
            toyaml = yaml.safe_load(yaml.dump(records))
            try:
                validateYaml(yamldoc=toyaml, schema=CRE_LINK_schema)
            except jsonschema.exceptions.ValidationError as ex:
                print(wsh.title + " failed validation")
                print(ex)
                return
            with open(os.path.join(cres_loc,wsh.title+".yaml"), "wb") as fp:
                fp.write(yaml.dump(toyaml,encoding='utf-8'))
        else:
            pass



def validateYaml(yamldoc: str, schema:str):
    jsonschema.validate(instance=yamldoc, schema=schema)


def pushToGithub(cre_loc:str, apikey, pullRequestName):
    repo = Repo(os.path.join(os.path.dirname(os.path.realpath(__file__)),"../../"))
    # sync first
    # repo.remotes.origin.pu()
    # create branch (cre_sync_timestamp)
    # if remote branch doesn't exist
    
    # all_branches = g.branch("-a")
    # remote_branches = filter(lambda branchName: "remotes" in branchName , g.branch("-a"))
    # if repo.active_branch.name not in remote_branches:
    #     g.branch("--set-upstream-to=origin/%s %s"%(repo.active_branch.name,repo.active_branch.name))
    g = Git()
    g.add(cre_loc)
    commit_msg = "cre_sync-%s"%datetime.now()
    g.commit("-m",commit_msg)
    repo.remotes.origin.push()
    # for r in repo.remotes:
    #     print(r.url)
    # pprint(r)


# No need to clone if this runs as a github action on a schedule
# https://www.jeffgeerling.com/blog/2020/running-github-actions-workflow-on-schedule-and-other-events
# def cloneCreRepo(targetFS):
#     pass


# def gitRemoteMerge(remote, local):
#     pass


def writeSpreadsheet(local, url):
    pass


spreadsheet_url = "https://docs.google.com/spreadsheets/d/1ACwnuvIwI6Lu3AikNUEeoc4wKoYd9wZ1eL4EtBP50kk/edit#gid=1618195737"
cre_loc = os.path.join(os.path.dirname(os.path.realpath(__file__)),"../../cres")
readSpreadsheet(spreadsheet_url, cres_loc=cre_loc)
pushToGithub(cre_loc,"","")
