# CRE Links

The biggest advantage of opencre.org is its ability to dynamically update itself by parsing other standards that link to it.

So far, as a small project, our approach to this has been relatively simple:

1. A security resource adds a link to `opencre.org` in their documents
2. The CRE team writes a parser for their specific document format and information structure
3. Add it to an ever-growing list of custom parsers that is maintained by the CRE team

Our best providers are those that are capable to either release big spreadsheets (e.g. CCM) or several structured Markdown files with one topic per section or file (Cheat sheet series, ASVS etc).

However, it makes things hard for:

1. single-page documents with several sections or information
2. mapping lots of small standards with their own unique structure

## Problem Statement

Human-readable documents can have several structures and links can have even more, parsing and understanding human language is an open problem in computing.
For example, there are likely non-NLP/AI ways to extract the correct link and title from a markdown file structured like this.

``` Markdown
# Document Title

## Relevant Title
[...]

## References
https://opencre.org/cre/<>

```

We could make an assumption that we always pick the document title as the name for each document that links to us but then what happens if we get 2 cre links for different purposes? A markdown file could contain multiple sections of information.

In general parsing this kind of human readable information, complicates the project beyond its scope and maintaining those solutions requires significant resources.

## Solutions

### Self contained Links

As standards integrate with the OpenCRE.org project, it would be intuitive for the authors to inject the information needed for the project to function with its maximum potential.
Then, not only does the parsing become simpler, but it also empowers us to use analytics to discover resources that link to us without our knowledge, helping the ecosystem grow faster.

The link for a standard could be as simple as:

``` url
https://opencre.org/cre/<creid>?type=<standard>&name=<standard_name>&section=<section>&link=<where should we redirect to>
```

And a link for a tool rule would be:

``` url
https://opencre.org/cre/<creid>?type=<tool>&name=<tool_name>&link=<where should we redirect to>&sectionID=<the tool rule id>
```

Under this proposal a link to e.g. CRE from ASVS becomes

``` markdown
You can read more information about secrets storage at (OpenCRE.org)[https://opencre.org/cre/223-780?name=ASVS&section=1.6.1&link=https://github.com/OWASP/ASVS/blob/v4.0.2/4.0/en/0x10-V1-Architecture.md]
```

And a link from ZAP's XSS rule could be

``` markdown
(CRE 028-726)[https://opencre.org/cre/028-726?name=ZAP&sectionID=15&link=https://github.com/zaproxy/zap-extensions/blob/main/addOns/ascanrules/src/main/java/org/zaproxy/zap/extension/ascanrules/PersistentXssScanRule.java]
````

### Abstract parser with config

Embedding all relevant information in every single link works very well for small resources with a few links and not extremely consistent resource structure. At the same time, it can become unwieldy for large, very well structured standards.
Luckily since there are limited formats aimed at both humans and machines we can write a generic parser that parses those formats and the repository owners can then provide configuration on where to find the relevant information for each link.
This use case is best described via an example.
Assuming the following markdown file:

``` markdown

# Session Management Cheatsheet

## Introduction

### Sub intro

## Section
### subsection

You can find more information about sessions in (opencre.org)[https://opencre.org/cre/<>]

#### sub-subsection

## References
* (cre)[https://opencre.org/cre/<>]

```

given a configuration file named `.cre.config.yaml` with the following content:

``` yaml
---
cre:
    contentPath: /foo/bar
    type: <standard|tool>
    name: "OWASP Cheatsheets"
    section: "closestParentH2"
    ignore: ["References"]
```

Where:

* contentPath instructs the parser to only look for cre links in the specific path relative to repo root.
* Type tells the parser what is the repository linked, it can be either "standard" to tell the parser that all documents are of type "standard" or "tool" to tell the parser that all documents are of type "tool".
* Name configures the global name for all elements of this document.
* Section configures where to find the document's "section" name relevant to the cre link. Allowed values will need to be in an enum and documented appropriately, in this example "closestParentH2" denotes that the parser should traverse the tree and find the first element that contains the link and is of markdown "Header-2" type.
* Ignore tells the parser to ignore cres contained in specific headers, this allows for excluding fields like "References/External-links" etc from convention.

If this file is set at the root of the repository we can then parse and automatically import the standard or tool whose content is described in this repo.
