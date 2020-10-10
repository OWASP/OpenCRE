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

# todo: generate schema from existing yaml, validate against schema
# issue pull request
# pull from github
# sync to spreadsheet
 
def readSpreadsheet(url:str):
    """given remote google spreadsheet url,
     reads each workbook into a yaml file in the local fs"""
    gc = gspread.oauth()
    sh = gc.open_by_url(url)
    for wsh in sh.worksheets():
        print(wsh.title)
        if wsh.title[0].isdigit():
            with open(wsh.title+".yaml","w") as fp:
                fp.write(yaml.dump(wsh.get_all_records()))
        else:
           pass
        #  print(yaml.dump(wsh.get_all_records()))


def convertToYaml(csv):
    pass

def pushToGithub(filePath, apikey):
    pass

def gitRemoteMerge(remote, local):
    pass

def writeSpreadsheet(local, url):
    pass

readSpreadsheet("https://docs.google.com/spreadsheets/d/1ACwnuvIwI6Lu3AikNUEeoc4wKoYd9wZ1eL4EtBP50kk/edit#gid=1618195737")
