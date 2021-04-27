Create Graph With OWASP Projects
===
Warning, this is highly experimental.
Main purpose is to showcase the metadata in `index.md`

This script is meant to parse a list of organisations and/or repositories which hold OWASP projects and create a mind map of them.
Resulting mindmap is organised by SDLC step the projects fit in, by default it categorises non-sdlc projects as general.
It uses a persistent sqlite3 file to cache results so it doesn't get throttled by Github.
Cache can be used to generate new data groupings or for further analysis.
Map generation is independed from data retrieval

Usage
----

Preferably in a virtual environment

```
pip install -r requirements.txt
GITHUB_USERNAME=<your username> GITHUB_TOKEN=<your github personal access token> python owasp_project_metadata_mindmap_gen.py
python owasp_project_metadata_mindmap_gen.py --from_cache script_cache.sqlite  # generate map from saved data
```

Output is a `map.dot`, `map.pdf` and a `map.svg` file.
For now these files only have basic data since most repos do not hold interesting metadata

Future Improvements
----

* Make into github action which runs on a cron schedule
* Add colours for each step of the SDLC and related items
* Improve project links
* Make interactive by creation of a github.io page with javascript that parses `map.dot` and at a minum provides usage instructions (and more info) in a sidepanel when clicking on a node.
* When projects update their index.md metadata, create a schema and validate metadata against the schema.
* fix unittests
