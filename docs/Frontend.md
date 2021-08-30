CRE Frontend
===

The frontend to the CRE project is a single page application that serves the following purposes:

* Demoes the CRE concept by allowing users to search contents either by standard, CRE id or name or by tag
* Allows users to select a number of standards and gives them the ability to export a mapping of the standards to each other. (Gap analysis use case)
* Gives users the ability to suggest a new mapping by submitting a link to a pre-filled spreadsheet template
* Allows users to see a Graph of how different standards map to each other

Search Functionality
---

The CRE search page is the front page of the CRE frontend and consists of a searchbar spanning most of the screen. A user can search either for one of the following:

* name of a standard with an optional section and subsection
* CRE by name
* CRE by id
* any document type by tag

The frontend then contacts the REST API and on successfull response shows the results by listing each Document returned and for each of it's links it provides a hyperlink to a search result of said document.
Each hyperlinked document also has a collapsible section that lists more information about it such as description, tags etc.

Gap analysis functionality
---

