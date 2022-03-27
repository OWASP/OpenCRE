CRE External Parsers
=

This directory contains a collection of parsers meant to import relevant links from specific projects.

Zap Alerts Parser

This parser is meant to parse ZAP Rules, find the CWEs they link to and if we know about those CWEs, link to the corresponding CREs

Cheatsheets Parser

This parser is meant to crawl the released cheatsheets directory and find links to CREs from a specific cheatsheet, then insert the cheatsheet and register those links.

Misc Tools Parser

The parser introduces the "Register Link" concept. This is simply a hyperlink to `opencre.org/cre/<cre-id>` specifying `register=true` in the query string and providing any other relevant information that should acompany this particular Document. The CRE application will then proceed to register the node with the information provided and link to the CRE identified inthe URL.
In this version only one link per Repository is supported. We welcome feature or pull requests with more support if there is interest.

Example

If your project is called `Foo` and you want to link it to CRE 111-111, the you can add the following in `README.md` located at your project's root.

```
Foo 
===
[...]
CRE Link:(111-111)[https://www.opencre.org/cre/111-111?register=true&type=tool&tool_type=Offensive&tags=secrets,training&description=any-description-you-want] 
```

This will register a one birectional link from opencre.org to your project and your project to opencre.org. 
