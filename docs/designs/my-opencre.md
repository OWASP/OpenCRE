# My OpenCRE


## Introduction 

Users asked for a way to include their own standards into opencre.
So far importing has been done via developers either writing importers or doing mappings manually and then running import jobs to populate a database from data sources.

These jobs are a pain as they are: 
* Cli only
* Require intimate knowledge of cre import format 
* Require intimate knowledge of existing cres

## The problem 

Currently users cannot run opencre locally and have the ability to layer their own data and policies on top of cre. The process is complicated and has a number of non user friendly points described above.

## The suggestion 

In V3 we allowed everyone to run cre locally while also giving them the ability to download upstream data on launch.

In v4 we should create 3 more features:


* Export cre structure as CSV
* Given a CSV describing a standard, use embeddings to suggest the nearest cre
* Given a CSV mapping cre to standard clauses, import the standard and calculate gap analysis 

## Exporting cre structure as CSV

This is useful for creating a templated import spreadsheet.
Given a populated opencre application instance users should be able to download a CSV that contains the structure of all CREs loaded in that instance.
The CSV should follow a format that we can use to import.
The cres should be presented stacked to show the hierarchical format.

## Populate CSV describing standard with CREs

This is useful for reducing the time it takes for mappings to be created.
The user-facing aspect of this functionality is a page where users can upload a file and in return after processing, they receive a file with the results.

Given a csv containing a resource that follows a specific format described below <export format but no CREs, only standard entries with title, section, section id, hyperlink and potentially text>, for every row of the standard, use the embeddings generation functionality and the similarity calculation functionality to suggest the nearest most appropriate cre entry if there is one. If not, leave empty.


## Import from CSV

Provide a page that when running in client mode, allows users to drag n drop a CSV that contains cre mappings following the format described above. OpenCRE then imports the mappings, calculates embeddings and gap analysis and notifies the user when it's done or on error.
When importing users can select to skip calculation of specific gap analysis or embeddings altogether.
