# Import V2

## Problem statement

The OpenCRE application has grown a lot in the past 4 years but the importing functionality has not.
Currently OpenCRE performs the following tasks in order to import and generate data:

* Import semantic structure & core resources from main csv
* Generate embeddings
* Import resources which have an importer
* Generate embeddings
* Calculate 700+ gap analysis structs and save them

No consideration for speed, efficiency or reproducibility has benn made during the development of the importing mechanism, due to the fact it is supposed to be very infrequent.
Furthermore importing can only be done by the developers.
As such a full data import and generation takes days since its all on a single core with little memory requirements and a very procedural approach.

For OpenCRE v3 a core goal is the ability to allow the community to import data so long as the core structure remains the same.
As such it is important that importing is faster and can be done per-resource as opposed to the all-or-nothing current approach.

## Solution

Importing needs to be heavily refactored in order to support fractionality and parallelisation.
Specifically the following changes are required:

1. change method `application.cmd.cre_main.parse_standards_from_spreadsheeet` to recognise our core CSV and first retrieve a list of included resources (be it CRE structure or external resources)

2. then change the same method to loop over resources and import each resource other than CREs in parallel.

3. change method `parse_hierarchical_export_format` to return a dict mapping the name of the resource to the documents of the resource so each resource can be split for importing to different workers
4. change method `application.cmd.cre_main.parse_standards_from_spreadsheeet` to prioritise largest standards for importing first.
5. change method `parse_hierarchical_export_format` to call both `register_cre` and `register_node`
6. change methods `register_cre/node` to also optionally generate embeddings, update neo4j and optionally precalculate two way gap analysis for each resource imported
7. change embedding generation to make it optional to calculate embeddings on singleton instantiation
8. write tests that allow of resource updating
9.  create a method that allows for "forgetting" a resource, useful for when our core structure changes This includes
    * remove all links between the target resource and everything else
    * remove all embeddings of the target resource
    * remove all gap analysis of the target resource
    * ensure method does not work for CREs