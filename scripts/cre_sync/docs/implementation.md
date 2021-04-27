CRE Utilities Implementation
===

Introduction
---

In order to implement the CRE v0.91 design defined [here|] and to ensure the [requirements|"./requirements.md"] are satisfied several utilities need to be created.
This application needs to be easily deployable and also define a feature-complete library which would allow for others to adopt the CRE structure.

Suggested Modifications:

* Interoperability: the fiels need to be parseable easily by widely used libraries, while the example files listed in the requirements document are valid YAML, a slightly modified format is suggested. Please refer to the section "File Format" for rationale and more information.

* Inter standard mapping: Allowing standards writers to submit a file where they map to a specific CRE is a good idea, it would be good to expand this by allowing standards writers to link to other standards as well, within the same mapping file.
This abstracts mappings away from a single standard and instead allows standards writers to provide a document hierarchy that contains CREs and/or other standards.

* The url for the refer use-case is of the form: `http://cre.com/refer?273-300` it is suggested to add a variable and thus transform it to:
`http://cre.com/273-300` this would enable the addition of other variables for future use cases, e.g.:
`http://cre.com/273-300&link=nist&link=asvs&link=top10-2017`

* Higher level concepts: TODO(Spyros): merge cregroups and cres, there is not point in making them different

* CRE Version Pinning, the TOP 10 project has asked for links to CREs as they were at a point in time. I don't have a good solution to this for mapping files, it could be solved by linking to a git sha but then I'm not sure how this would work for the frontend, an alternative would be to make every CRE, Standard and Link versioned and link against a version, but then they loose all the new mappings.

File Format (Source Parser)
---

For parser simplicity and to allow for targetting more entities in the future, the following file modification is suggested.
A generic 'Document' is proposed.
A document is a parser input file and defines the information that an input file could have.
This information is

```Text
    doctype : what kind of document this is
    id : [Optional] an id for this specific document, can be a CRE id, needs to be unique for this type of document
    description : [Optional] human readable description
    name : a human readable name for this document, usage depends on the doctype.
    links : [Optional] a list of Links to other documents, essentially a structure of (LinkType: <type>, Document:document)
    tags : [Optional] a list of strings that add attributes to this document
    metadata : [Optional] a list of key value pairs of arbitrary strings

```

Using this document format a Standard link file can look like the following

```Yaml
description: ''
doctype: Standard
id: ""
name: ASVS
section: 1.1.1
subsection: ""
hyperlink: ""
links:
- type: 'SAM'
  tags: []
  document:
    description: 'Some description'
    doctype: CRE
    id: 001-005-020
    links: []
    metadata: {}
    name: CRE-NAME
    tags: []
- type: 'SAM'
  tags: []
  document:
    description: 'Another description'
    doctype: CRE
    id: 010-007
    links: []
    metadata: {}
    name: CRE007
    tags: []
- type: 'SAM'
  tags: []
  document:
    description: 'A standard Description'
    doctype: Standard
    id: ""
    name: Top10-2017
    section: 2
    subsection: 3
    links: []
    metadata: {}
    tags: []
    hyperlink: "https://blahblah"
```

This would tell the parser that ASVS 1.1.1 links to CRE001-005-020 and CRE010-007 and Top10-2017 item 2. All links are of the type 'SAM'

The equivalent information CRE document, would be:

```Yaml
description: ''
doctype: CRE
id: 010-007
name: 'Some Name'
links:
- type: 'SAM'
  tags: []
  document:
    description: 'Some description'
    doctype: CRE
    id: 001-005-020
    links: []
    metadata: {}
    name: CRE-NAME
    tags: []
- type: 'SAM'
  tags: []
  document:
    description: ''
    doctype: Standard
    id: ""
    name: ASVS
    section: 1.1.1
    subsection: ""
    hyperlink: ""
- type: 'SAM'
  tags: []
  document:
    description: 'A standard Description'
    doctype: Standard
    id: ""
    name: Top10-2017
    section: 2
    subsection: 3
    links: []
    metadata: {}
    tags: []
    hyperlink: "https://blahblah"
```

While this format is significantly longer than the one suggested in requirements.md , it allows for more complete mappings to be written. It also allows for the format to be preserved regardless of the user journey.
A standards writer can submit the 'standard' example above and we can export/provide the 'CRE' format as they are different views of the same information.

Mappings from a Spreadsheet (Sheet Parser)
----

Providing standards writers and community members the ability to submit a url linked to a Google spreadsheet and the application/parser import CRE mappings from there is a good idea, however care must be taken to ensure the spreadsheet is acutally parseable.
In order for this to happen a robust template must be created and a parser from/to this template needs to be written.

Since the design outlined in requirements.md is simple no more information is required at this stage.

CRE WebApp & Query Engine
---

For CRE to be easily browsable a web application needs to be created. The application should implement the "refer" use case at a minimum.

Backend
---

Internal Storage
---

A database needs to be created to hold all CRE information.
The database management engine SQLITE3 has been chosen for simplicity and due to it's ability to be portable. This database has 4 tables

* 'Standard' holding a mirror of the "Standard" document
* 'CRE' holding a mirror of the CRE document with the addition of the boolean field is_group that tells us if this CRE is considered a "higher level" concept.
* 'Links'holding a many to many mapping of CRE.id to Standard.id and two fields to store tags and the link type.
* 'InternalLinks' holding a many to many mapping of CRE.id to CRE.id and two fields to store tags and the link type. At least one of the CREs needs to be tagged as a group.

Parsers
---

There needs to be 2 distinct parser/input formats.

* Structured spreadsheets where given a reachable google spreadsheets url, containing CRE mappings the Backend creates associations and relevant mappings
* Files, where given a file containing one or more CRE mapping documents the backend generates all the necessary association.

To achieve this, a 2 parsers and a validator will be created that allow transformation from the Spreadsheet format to an internal format and validation. The other parser is a simpler 1:1 mapping between the file documents and the internal format.
The internally formatted documents can then be written to the database.

Since CRE files will be public domain, the parser should ideally be a library so other CRE users can benefit from this.

Frontend
---

A solid and user friendly frontend is necessary for the CRE project.
The frontend needs to be able to at least return a CRE and it's links if a user searchs for it. (The Refer use case)

Read CRE by ID (Refer)
---

When the user browses to `<domain>?creId=<X>` the frontend should return the CRE with id X and all it's links be it other CREs or Standards. Full information should be provided for all of them.

*Question:* Do we return transient links?
E.g. given a state of:

``` Text
CRE-010-007-Encryption -> CRE-010-008-Encryption-At-Rest -> CRE-010-009-Encryption-of-Financial-data-at-rest -> PCI-123
                \                       \
                 NIST-XYZ                 ASVS-1.2.3
```

And a query of `<domain>?creId=010-007`
Do we return:
a. CRE-010-007, NIST-XYZ, CRE-010-008-Encryption-At-Rest  <--- One level of mapping
b. CRE-010-007 links to (NIST-XYZ, CRE-010-008 links to (ASVS-1.2.3, CRE-010-009 links to (PCI-123))) <--- all levels, including transient

option a can require a lot of queries to get a full picture
option b can return a mountain of data

Read Mappings by URL (Refer++)
---

When the user browses to `<domain>?creId=<X>&link=CWE&link=ASVS` the frontend should return the CRE with id X and all it's links to CWE and ASVS, no other CREs or Standards should be returned.

Exporting
---

A user should be able to store/save the results of a query by having the ability to export the results to a CRE mapping document or a spreadsheet.

Export to files
---

Questions:

* Do we export per Group?
* Per CRE?
* Per Standard?

Resolved after talks with Ellie: let's create an export version for everything


```Text
who's our main consumer for the exported files?

* if it's standards writers -> per Standard
* if it's for us or other CRE integrators who are likely to want to have the whole database then we could export per Group
* if it's for a combination, perhaps we can export per CRE
```

* how dense we want the files to be? e.g. do we want to have standards->cres->all-groups  in one file? this could make the file very long. an alternative is to have a file per level of mapping such as:

``` python
for each CRE:
    add what it directly links to
write_file
```

as opposed to:

``` python
for each CRE:
    for each link:
        if link is Standard:
            add
        else if link is CRE:
            recurse
write-significantly-longer-file
```

The second option can potentially export the entire database if the CRE requested is somehow a root CRE in the tree.

this is not a problem anymore if we export by standard but then there's a lot of links between documents
since each export document will describe one standard section, subsection and all the CREs that particular standard links to

we could start with the second pseudocode mentioned above and iterate based on user feedback.

Submit/Add CRE
---

[Future feature/non-mvp]
Using pull requests to a repository would make a lot of sense, reviews are then public and the CRE files are always public and versioned.

Search Based On Tags (connections implementation)
---

[Future feature/non-mvp]
Given a url of `<domain>?tag=ops&tag=dfir&tag=encryption` the frontend returns all CREs and links that are tagged with all 3 tags.
