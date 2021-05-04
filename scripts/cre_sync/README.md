
Common Requirements Enumeration Application
===============================

This is work in progress.

This python web and cli application handles adding and presenting CREs.

Installing
---

To install this application you need python3.
Clone the repository
`git clone <repository>`
Launch a virtual environment, 
`virtualenv -p python3 venv/ && source venv/bin/activate`
install the dependencies with pip
`pip install -r scripts/cre_sync/requirements.txt`

Running
-------

To run the cli application, you can run `python cre.py --help`
To download a remote cre spreadsheet locally you can run
`python cre.py --review --from_spreadsheet https://docs.google.com/spreadsheets/d/19YBNcZHL9BF2Dw9Ijzqogc6MUyhTcH10Cb-37rBTFbk/edit\#gid\=1975949890`

To add a remote spreadsheet to your local database you can run
`python cre_main.py --add --from_spreadsheet https://docs.google.com/spreadsheets/d/1THhpJWrH7RVwEnawEOO-3ZQwuiAKEUyb_ZAdQnvHNsU`

To run the web application for development you can run
`FLASK_APP=cre.py flask run`

To run the web application for production you need gunicorn and you can run from within the cre_sync dir
`gunicorn cre:app --log-file=-`

Developing
---

You can run backend tests with `FLASK_APP=cre.py FLASK_CONFIG=test flask test`

Development Notes
---

add tests
   ~ defs --- Done
   ~ db -- Done
   ~ parsers -- Done   --- needs edge cases
    mapping_add -- Done for important methods, -- argparse logic only remains
   ~ spreadsheet_utils ~ -- Done
   frontend

* ~ add parse from export format ~ Done
* ~ add parse from export format where the root doc is a standard and it links to cres or groups ~ Done
* ~ add parse from spreadsheet with unknown standards (for key,val in items add_standard) ~ Done
* ~ merge spreadsheet to yaml and mapping add, they do the same thing ~ Done
* ~ add the ability for standards to link other standards, then you can handle assigning CREs yourself ~ Done
* ~ support importing yaml export files of more than 1 levels deep ~ Done
* ~ add export for Standards unmapped to CREs as lone standards (useful for visibility) ~ Done
* ~ add sparse_spreadsheet_export functionality one level of mapping per row, either everything that maps to standard X or everything that maps to CRE x ~ Done
* ~ add parse from export format ~ Done
* ~ add github actions ci ~ Done
* ~ make into flask rest api ~ Done
* ~   refer use case (search by cre) ~ Done
* ~   search by standard ~ Done
* ~ add the ability for a mapping document to have multiple yamls in it ~ Done

* add db integration of tags
* ~ add tags in db  (search by tag, export with tags etc) ~ Done 
* add parser integration of tags (parse the new new new spreadsheet template which incorporates tags)
* ~ add search by tag in rest and frontend ~ Done

* write frontend
* make frontend show Graph

* make pagination also for tag results
* make results per page a config item from env
* add flask cover command from here https://github.com/miguelgrinberg/flasky/blob/master/flasky.py#L33
* make library out of file format and spreadsheet template parsers
* add conditional export (select the standards you want exported and if you want to see the CRE ids or not, get spreadsheet with mappings)  (gap analysis use case)
* write docs and record usage gif
* add dockerfile???