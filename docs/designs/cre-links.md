# CRE Links

The biggest advantage of opencre.org is its ability to dynamically update itself by parsing other standards that link to it.

So far, as a small project, our approach to this has been relatively simple:
1. A security resource adds a link to `opencre.org` in their documents
2. The CRE team writes a parser for their specific document format and information structure
3. Add it to an ever-growing list of custom parsers that is maintained by the CRE team

This works relatively well for big, well-structured projects that have sufficient automation to either release big spreadsheets (e.g. CCM) or several simply structured Markdown files with one topic per section/file (Cheatsheets, ASVS etc).

However, it fails for single-page documents with several sections or information and for mapping lots of small standards which will likely have their own unique structure each.


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
We could make an assumption that we always pick the document title as the name for each document that links to us but then what happens if we get 2 cre links for different purposes? A markdown files could contain multiple sections of information.

In general parsing this kind of human readable information, complicates the project beyond its scope and maintaining those solutions requires significant resources.

## Solution
Since standards writers are already required to provide links to opencre.org why not get them to encode all the information we need in the link?
Then, not only does the parsing become simpler but we can also use analytics to discover resources that link to us but we may not know off yet.

The link for a standard could be as simple as:

```
https://opencre.org/cre/<creid>?type=<standard>&name=<standard_name>&section=<section>&link=<where should we redirect to>
```
The link for a tool rule could be as simple as:

```https://opencre.org/cre/<creid>?type=<tool>&name=<tool_name>&link=<where should we redirect to>&ruleID=<the tool rule id>
```


Under this proposal a link to e.g. CRE from ASVS becomes

```
You can read more information about secrets storage at (OpenCRE.org)[https://opencre.org/cre/223-780?name=ASVS&section=1.6.1&link=https://github.com/OWASP/ASVS/blob/v4.0.2/4.0/en/0x10-V1-Architecture.md]
```

And a link from ZAP's XSS rule could be

```
(CRE 028-726)[https://opencre.org/cre/028-726?name=ZAP&ruleID=15&link=https://github.com/zaproxy/zap-extensions/blob/main/addOns/ascanrules/src/main/java/org/zaproxy/zap/extension/ascanrules/PersistentXssScanRule.java]
````
