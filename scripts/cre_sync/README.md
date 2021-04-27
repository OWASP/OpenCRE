CRE Spreadhsheet to Github Sync
===============================

This script can be run either manually or via Github Actions.
The Github Action is run on a cron schedule defined in .github/ .
It syncs the contents of the spreadsheets with links between CREs and other external entities to CRE yaml files on Github.
There is a different Github Action which syncs those Yaml files to a CRE REST API for querying.

Assumptions
-----------

* The URLs of the auto-synced spreadsheets are defined in the ```spreadsheets.txt ``` file. One URL per line.
* All spreadsheets need to follow the template defined by ```CRE_LINK_schema```, the script will ignore any workbooks that do not follow the schema
* Only workbooks whose names start with a number will be synced, this is on purpose to allow pivot tables or other miscelaneous/WiP workbooks.
* You _need_ to share the spreadsheet to be synced with the following email: ```project-integratio-sync-servic@project-integration-standards.iam.gserviceaccount.com``` (this script's service account)
* This script creates Pull Requests, this is important so CRE elements can be manually reviewed.

Running
-------

This script runs automatically, if you want to run it yourself against your own spreadsheet you need the following:

* Setup gspread for you, if you want to run this script as a user you are looking for an OAUTH token, otherwise you need a Service Account: https://gspread.readthedocs.io/en/latest/oauth2.html#enable-api-access
* Setup a github api token with access to your repository: https://github.com/settings/tokens
* From within this repository and with the ability to push to github with an SSH key run: 
`GITHUB_API_KEY="<your github api key>" python ./spreadsheet_to_yaml.py`

Notes
---

add tests
   ~ defs --- Done
   ~ db -- Done
   ~ parsers -- Done   --- needs edge cases
    mapping_add -- Done for important methods, -- argparse logic only remains
   ~ spreadsheet_utils ~ -- Done
   Frontend

* ~ add parse from export format ~ Done
* ~ add parse from export format where the root doc is a standard and it links to cres or groups ~ Done
* ~ add parse from spreadsheet with unknown standards (for key,val in items add_standard) ~ Done
* ~ merge spreadsheet to yaml and mapping add, they do the same thing ~ Done
* ~ add the ability for standards to link other standards, then you can handle assigning CREs yourself ~ Done
* ~ support importing yaml export files of more than 1 levels deep ~ Done
* ~ add export for Standards unmapped to CREs as lone standards (useful for visibility) ~ Done
* ~ add sparse_spreadsheet_export functionality one level of mapping per row, either everything that maps to standard X or everything that maps to CRE x ~ Done
* ~ add parse from export format ~ Done

* ~ make into flask rest api ~ Done
* ~   refer use case (search by cre) ~ Done
* ~   search by standard ~ Done
* add db integration of tags
   * ~ add tags in db  (search by tag, export with tags etc) ~ Done 
   add parser integration of tags (parse the new new new spreadsheet template which incorporates tags)
   ~ add search by tag in rest and frontend ~ Done

write frontend
make frontend show Graph

make library out of file format and spreadsheet template parsers
add the ability for a mapping document to have multiple yamls in it
add conditional export (select the standards you want exported and if you want to see the CRE ids or not, get spreadsheet with mappings)  (gap analysis use case)
write docs and record usage gif
add dockerfile???

add github actions ci/cd
