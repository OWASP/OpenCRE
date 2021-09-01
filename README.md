

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![GitHub Super-Linter](https://github.com/OWASP/common-requirement-enumeration/workflows/Lint%20Code%20Base/badge.svg)](https://github.com/marketplace/actions/super-linter)
[![GitHub CodeQL](https://github.com/OWASP/common-requirement-enumeration/workflows/CodeQL/badge.svg)](https://github.com/marketplace/actions/codeql-analysis)
[![Main Branch Build](https://github.com/OWASP/common-requirement-enumeration/workflows/Test/badge.svg?branch=main)](https://github.com/OWASP/OWASP/common-requirement-enumeration/workflows/Test)

Common Requirements Enumeration Application
===============================

This is work in progress.

This python web and cli application handles adding and presenting CREs.

Installing
---

To install this application you need python3.
Clone the repository:
<pre>git clone <repository></pre>
Launch a virtual environment:
<pre>virtualenv -p python3 venv/ && source venv/bin/activate`</pre>
Install the dependencies with pip:
<pre>pip install -r requirements.txt</pre>
Copy sqlite database to required location
<pre>cp cres/db.sqlite standards_cache.sqlite</pre>


Running
-------

To run the CLI application, you can run
<pre>python cre.py --help</pre>
To download a remote cre spreadsheet locally you can run
<pre>python cre.py --review --from_spreadsheet <google sheets url></pre>

To add a remote spreadsheet to your local database you can run
<pre>python cre_main.py --add --from_spreadsheet <google sheets url></pre>

To run the web application for development you can run
<pre>FLASK_APP=cre.py flask run</pre>

Alternatively, you can use the dockerfile with
<pre>docker build -f Dockerfile-dev -t csync . && docker run -it -p 5000:5000 csync</pre>

To run the web application for production you need gunicorn and you can run from within the cre_sync dir
<pre>gunicorn cre:app --log-file=-</pre>

Developing
---

You can run backend tests with
<pre>FLASK_APP=cre.py FLASK_CONFIG=test flask test</pre>
You can run get a coverage report with `FLASK_APP=cre.py FLASK_CONFIG=test flask test --coverage`
Try to keep the coverage above 70%

Repo Moved here from https://github.com/northdpole/www-project-integration-standards


Development Notes
---

- [ ] add tests
- [x] defs 
- [x] db 
- [x] parsers 
- [ ] mapping_add  ( done for important methods ) argparse logic only remains
- [x] spreadsheet_utils
- [ ]  frontend

- [x] add parse from export format 
- [x] add parse from export format where the root doc is a standard and it links to cres or groups 
- [x] add parse from spreadsheet with unknown standards (for key,val in items add_standard) 
- [x] merge spreadsheet to yaml and mapping add, they do the same thing 
- [x] add the ability for standards to link other standards, then you can handle assigning CREs yourself 
- [x] support importing yaml export files of more than 1 levels deep 
- [x] add export for Standards unmapped to CREs as lone standards (useful for visibility) 
- [x] add sparse_spreadsheet_export functionality one level of mapping per row, either everything that maps to standard X or everything that maps to CRE x 
- [x] add parse from export format 
- [x] add github actions ci 
- [x] make into flask rest api 
- [x] > refer use case (search by cre) 
- [x] > search by standard 
- [x] add the ability for a mapping document to have multiple yamls in it 
- [x] add db integration of tags 
- [x] add tags in db  (search by tag, export with tags etc)  
- [x] add parser integration of tags (parse the new new new spreadsheet template which incorporates tags) 
- [x] add search by tag in rest 
- [x] add dockerfile 
- [x] add conditional export (select the standards you want exported get mappings between them)  (gap analysis use case) ~ -- Done
- [x] add flask cover command from here https://github.com/miguelgrinberg/flasky/blob/master/flasky.py#L33
- [x] Make Standards versioned ~ -- Done
- [x] write frontend  
- [x] make results per page a config item from env 
- [x] migrate to new repo 
- [x] add black autoformater 
- [x] merge frontend changes to master 
- [x] Typed Python? 

= Future Considerations =

- [ ] improve test coverage -- we are at 73%, let's increase to 80%

- [ ] Make frontend show gap analysis
- [ ] Make frontend export search results and gap analysis to spreadsheet (supply backend with an "export=True" arg)
- [ ] Make frontned able to import from spreadsheet template.
- [ ] Make frontend able to import from files
- [ ] Make frontend able to import by filing in a form.
- [ ] make pagination also for tag results and gap analysis
- [ ] make library out of file format and spreadsheet template parsers
- [ ] add more linkTypes, Child, Controls, Tests, others.
- [ ] Add more Document types, Tool, Library
- [ ] Figure a way to dynamically register new Custom Resource Definitions and register custom logic on what to do on import/export and search.
- [ ] write docs and record usage gif
