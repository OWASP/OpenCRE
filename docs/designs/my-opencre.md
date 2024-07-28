# My OpenCRE


## Introduction 

Users asked for a way to include their own standards into opencre, sometimes with the added need to run OpenCRE at their own premises because of confidentiality.
Why?
This alllows them to use search, browse, refer, map analysis and chat on an integrated and tailored platform - organizing their guidelines, policies, and requirements according to the OpenCRE catalog and by doing so, linking everything to the key industry security standards.

So far, importing standards has been done via developers either writing importers or doing mappings manually and then running import jobs to populate a database from data sources.

Currently this requires: 
* Command-line interactions only
* Intimate knowledge of the cre import format 
* Intimate knowledge of the OpenCRE catalog structure

## The problem 

Currently users cannot run opencre locally and even if they could, adding their own standards is currently an OpenCRE expert job: difficult.

## The suggestion 

Allow OpenCRE to be run locally by providing a container, streamlining some data initialization processes, and providing documentation. In the begining of July 2024 we accomplished this through the release of OpenCRE V3.

In v4 we intend to create 3 more features:

* Mapping template export: Export the OpenCRE catalog as mapping template to contribute mappings between the cre catalog and a standard in CSV format
* Initial automated standard matching: Given a CSV containing a standard with a requirement in each row, use embeddings to match the nearest cre for every requirement in the standard and populate the mapping template for review
* Import standard: Given a populated mapping template and a CSV containing a standard, import the standard and calculate gap analysis
* Provide an easy interface to manage imported standards

V5 will feature:
* Change OpenCRE Catalog: Allow an organization to use the mapping template to make changes in the OpenCRE catalog by completely replacing how existing Common Requirements are related, and by adding or removing Common Requirements.

Until Version 5, the mapping template can be used to communicate suggestions to the OpenCRE catalog, that will then be processed by the OpenCRE team, and provided as downloadable for local MyOpenCRE implementations.

## Mapping template export

This is useful for creating a templated import spreadsheet.
Given a populated opencre application instance, users should be able to download a CSV that contains the structure of all CREs loaded in that instance.
The CSV should follow a format that we can use to import.
The cres should be presented stacked to show the hierarchical format.

## Initial automated standard matching

This is useful for reducing the time it takes for mappings to be created.
The user-facing aspect of this functionality is a page where users can upload a file and in return after processing, they receive a mapping template file with the results.

Given a csv containing a resource that follows a specific format described below <export format but no CREs, only standard entries with title, section, section id, hyperlink>, for every row of the standard, use the embeddings generation functionality and the similarity calculation functionality to suggest the nearest most appropriate cre entry if there is one. If not, leave empty.


## Import from CSV

Provide a page that when running in client mode, allows users to drag and drop a CSV that contains cre mappings following the format described above. OpenCRE then imports the mappings, and gap analysis and notifies the user when it's done or on error.
Optionally users can provide the standard file, so that it can be incorporated in the OpenCRE Chat repository (add text, calculate embedding).
When importing users can select to skip calculation of specific gap analysis or embeddings altogether.
