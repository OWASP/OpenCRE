CRE Utilities Implementation
===

Introduction
---

In order to implement the CRE v0.91 design defined [here|] a web based application needs to be created.
This application needs to be easily deployable and also define a feature-complete library which would allow for others to adopt the CRE structure.

The CRE Design linked to above, lists the following components:

* Sheet Parser
* Source Parser
* CRE WebApp
* CRE query engine

It also lists the following requirements:

[Requirement] Source Parser
---

A CRE source document, needs to include the following information as a minimum:

``` Yaml

# Mapping file WSTG

Segment short name (optional): CRYP-04
Segment long name (optional): Testing for weak encryption
URL: https://owasp.org/www-project-web-security-testing-guide/v41/4-Web_Application_Security_Testing/09-Testing_for_Weak_Cryptography/04-Testing_for_Weak_Encryption.html
CRE-ID: 273-300. (In case a segment links to multiple CRE's, multiple entries can be specified, or the CRE-ID's can be enumerated in the CRE-ID field. For example: CRE-ID: 273-300, 251-823)
Link Type (optional, default is DTA): DTA (others are: SAM=same, SIM=similar, IPO = is part of)
```

[Requirement] Parser use case
---

The CRE source parser scans a set of source files in a folder structure. The source files contain at a minimum the information above.
For every hyperlink to CRE it generates an entry with:

* the extracted CRE number
* an optional section name – in this case extracted from the first item above the hyperlink with class ‘section’
* a hyperlink to the WSTG document.

[Requirement] Higher Level Concepts
---

We need higher-level abstract CRE topics that we can link higher level Standard's topics to.
Within the CRE administration we can then define relations between those higher level CREs and lower level CREs.

[Requirement] Higher Level Mapping File Example
---

Given the following documents:

* Core CRE entries:

``` Yaml
CRE-ID: 273-300
Description: “Encrypt personal data at rest”
CRE-ID: 280-911
Description: “Encryption”
CRE-ID: 571-433
Description: “Personal data protection”
```

* Mapping file WSTG

``` Yaml
Segment short name (optional): CRYP-04
Segment long name (optional): Testing for weak encryption
URL: https://owasp.org/www-project-web-security-testing-guide/v41/4-Web_Application_Security_Testing/09-Testing_for_Weak_Cryptography/04-Testing_for_Weak_Encryption.html
CRE-ID: 273-300. (In case a segment links to multiple CRE's, multiple entries can be specified, or the CRE-ID's can be enumerated in the CRE-ID field. For example: CRE-ID: 273-300, 251-823)
Link Type (optional, default is DTA): DTA (others are: SAM=same, SIM=similar, IPO = is part of)
```

* Mapping file ASVS

``` Yaml
Segment short name (optional): 6.1.1
Segment long name (optional): Encrypting personal data at rest bla bla
URL: https:SVS bla
CRE-ID: 273-300
Link Type (optional, default is DTA): SAM (others are: SAM=same, SIM=similar, IPO = is part of)
```

* Mapping file NIST

``` Yaml
Segment short name (optional): SC-12
Segment long name (optional): Cryptographic Key establishment and management
URL: NISTbla bla pdf
CRE-ID: 280-911
Link Type (optional, default is DTA): DTA (others are: SAM=same, SIM=similar, IPO = is part of)
```

The parser would produce the following links:

``` Text
CRE-273-300 -> WSTG-CRYP-04
            \
              ASVS-6.1.1

CRE-280-911 -> NIST-SC-12

CRE-571-433 -> <No link>
```

The CRE system would also store all the other information for every standard such as

* Segment short name
* Segment long name
* URL
* Link Type

[Requirement] Refer Use Case
---

Given a link of the form: ```http://cre.com/refer?273-300``` the CRE Web Application returns the following information:

```Yaml
Title: CRE 273-300 "Encrypt personal data at rest"

Same:
-ASVS V6.1.1

Similar:
- CWE-311: (Missing Encryption of Sensitive Data)

Is part of:
- OWASP Top 10 A3 (Sensitive data exposure)

Discusses topic aspects:
- OWASP WSTG – CRYP-04 (Testing for weak encryption)
- CRE Encryption
- CRE Personal data protection
```

The refer page shows the CRE ID and description, then for every link type it lists the links.
Links can take the user to the respective source or to another CRE page, such as ‘Encryption’

[Requirement] Stacked High level concepts
---

Given:

* `CRE 956-220 "Encrypt health data at rest"` that links to `CRE 155-326 Encryption of data at rest`
* `CRE 273-300 "Encrypt personal data at rest"` that links to `CRE 155-326 Encryption of data at rest`
and
* `CRE 155-326 Encryption of data at rest` that links to `CRE 280-911 Encryption`

Any standard or cre link to either of `CRE 956-220` or `CRE 273-300` lead to a transient link to `CRE 280-911 Encryption`


[Requirement] Spreadsheet Management
---

Given a table/spreadsheet with the following structure


+-----+-------+-------+-----+-------------------------------+------------+------------------+---------------+
| Row | ASVS  | NIST  | CWE |          Description          |   Group1   |      Group2      |    Group3     |
+-----+-------+-------+-----+-------------------------------+------------+------------------+---------------+
|   1 | 6.1.1 |       | 123 | Encrypt personal data at rest | Encryption |  Encrypt at rest | Personal data |
|   2 | 60102 |       |     | Encrypt health data at rest   | Encryption |  Encrypt at rest |               |
|   3 |       | SC-12 |     | Encryption                    | Encryption |                  |               |
+-----+-------+-------+-----+-------------------------------+------------+------------------+---------------+

The parser creates 5 CREs with four source links:
CREs:

* CRE1 : `Encrypt personal data at rest`
* CRE2 : `Encrypt health data at rest`
* CRE3 : `Encryption`
* CRE4 : `Encrypt at rest`
* CRE5 : `Personal data`

Links:

* CRE1 -> ASVS 6.1.1. and CWE 123
* CRE2 -> ASVS 6.1.2
* CRE3 -> NIST SC-12, internally linking to CRE1 and CRE2
* CRE4 -> internally linking to CRE1 and CRE2
* CRE5 -> internally linking to CRE1

[Requirement] MVP implementation steps
---

The CRE MVP lets three sources refer to CRE pages that contain links to the sources, on a selection of topics.

1. Select three data sources (say ASVS, Cheat sheets and WSTG)
2. Pick a small selection in the most detailed source (e.g. ASVS) - say session management and login functionality
3. Specify the file format for the Mapping file (should be easy to edit and read for everybody) – see design
4. Build the CRE Updater that reads the mapping file and builds the Sources, CRE-Source relations and CRE entries tables
5. Design the CRE parser that scans the source files for marked CRE id’s and creates a mapping file automatically.
6. If the CRE parser is very hard to build: we go for MVP-noparse. Otherwise we go for MVP-parse.

[Requirement] Alternative A MVP-noparse
---

Create the first Mapping file, say based on ASVS.
Each CRE mentioned is new and needs a name specified. Do this for a small selection.
Create a second mapping file for another source. Do this for the CREs that just have been identified and try to find the right sections.
Around those sections may also be some new CRE’s – perhaps CRE’s on a higher level than a technical control. Also add those.
Do the same for the third mapping.

Add the CRE hyperlinks to the referred sections in the corresponding sources.
Build the webapp that shows a link page for a CRE, with references to the different sources.

[Requirement] Alternative B MVP-parse (preferred because zero maintenance)

Start adding CRE links in the original content of the first source, say the ASVS.
Each CRE mentioned is new and needs a name specified. Do this for a small selection.
For the CREs that just have been identified, add links to those in the second source. Around those sections may
also be some new CRE’s – perhaps also CRE’s on a higher level than a technical control. Also add those.
Do the same for the third mapping.
Build the parser. It recognizes the CRE links in the original content and constructs a hyperlink base on the context.
The links themselves are published as hyperlinks to the CRE webpage.

[Requirement]After the MVP: connections
---

Connections are a way, similar to slices and tags, to connect CRE’s that have a relation, for example all CRE’s that require involvement of
Ops, or all CRE’s that fall under session management
Connections can be used to define groups by referring to a CRE’s that presents a group, or maybe just a group and not a requirement (eg.
All Java requirements). These groups can then also link to other groups.

There are two ways to administer connections: externally: by defining a group through a group record and from there refer to CRE’s and
other groups, internally: add connection data to a group in CRE records.

Option 1: Group administration – manage externally
Given the following

``` Yaml
CRE12452

Name: Appsec-Session-TokenGeneration
- ASVS 145, 146
- WSTG
- NIST
- CWE

CRE12451

Name: Appsec-Session-Removal
- ASVS 141
- WSTG
- NIST
- CWE

CRE12459

Name: “Session management”
Connect CRE12451
Connect CRE12452
- Proactive Controls

```

Webpage renders

CRE12459 “Session management”

* [Proactive Controls|]
* [CRE12452 -Appsec-Session-TokenGeneration|]
* [CRE12451 -Appsec-Session-Removal|]

Option 2: Group administration – manage internally

Given:

``` Yaml
CRE12452
Name: Appsec-Session-TokenGeneration
Connect: CRE12459
- ASVS 145, 146
- WSTG
- NIST
- CWE

CRE12451

Name: Appsec-Session-Removal
Connect: CRE12459
- ASVS 141
- WSTG
- NIST
- CWE

CRE12459
Name: “Session management”
- Proactive Controls
```

Webpage renders

CRE12459 “Session management”

* [Proactive Controls|]
* [CRE12452 -Appsec-Session-TokenGeneration|]
* [CRE12451 -Appsec-Session-Removal|]


[Requirement] Hierarchy
---
The Connect mechanism can be used to define the hierarchy, but it needs an additional aspect: direction, because otherwise there is no way to distinguish between connections to parents and to children. This can be done by making parent/child a property of a connection, OR use the internal external administration to distinguish.
Another challenge is that not every connection will be part of a hierarchy so we would need to distinguish between hierarchy groups and other group, plus allow to select a specific hierarchy as the one to use for navigation.

How would hierarchy administration work – option 1 (parent/child property)
Given:

``` Yaml
CRE12452
Name: Appsec-Session-TokenGeneration
Connect(Parent) CRE12459
Group(Child) CRE12456
Group(Child) CRE12457
- ASVS 145, 146
- WSTG
- NIST
- CWE

CRE12456
Name: Appsec-Session-TokenGeneration-entropy
- ASVS 161
- NIST

CRE12457
Name: Appsec-Session-TokenGeneration-entropy
- ASVS 162

CRE12459
Name: Session management
- Proactive Controls
```

Web Page renders:

``` Yaml
CRE12452 -Appsec-Session-TokenGeneration
- ASVS 145, 146
- WSTG
- NIST
- CWE

Parent: “Session management”
Children:
- Appsec-Session-TokenGeneration-entropy
- Appsec-Session-TokenGeneration-cryptornd

Other groups:
- Webappsec
```

Note that it’s not necessary to specify with CRE12456 that
12452 is its parent, since 12452 already refers to 12456 as its child.

How would hierarchy administration work – option 2 (use direction ofreference)
Given:

``` Yaml
CRE12452
Name: Appsec-Session-TokenGeneration
Group CRE12456
Group CRE12457
- ASVS 145, 146
- WSTG
- NIST
- CWE

CRE12456
Name: Appsec-Session-TokenGeneration-entropy
- ASVS 161
- NIST

CRE12457
Name: Appsec-Session-TokenGeneration-entropy
- ASVS 162

CRE12459
Name: Session management
Group CRE12452
- Proactive Controls
```

Page renders:

``` Yaml

CRE12452 -Appsec-Session-TokenGeneration
- ASVS 145, 146
- WSTG
- NIST
- CWE

Parent: “Session management”
Children:
- Appsec-Session-TokenGeneration-entropy
- Appsec-Session-TokenGeneration-cryptornd

Other groups:
- Webappsec
```

Note that it’s not necessary to specify with CRE12456 that 12452 is its parent, since 12452 already refers to 12456 as its child.

[Example] CRE mapping data model, with example data
---

``` Yaml
Source name: OWASP Web Security Testing Guide
Source short name: OWASP WSTG
Source landing page URL: https://owasp.org/www-project-web-security-testing-guide/v41/
Version at moment of mapping: v4.1

<followed by a list of CRE entries, linking segments of the source to CRE-ID's in a many to many relation>

Segment short name (optional): 4.9.4
Segment long name (optional): Testing for weak encryption
URL: https://owasp.org/www-project-web-security-testing-guide/v41/4-Web_Application_Security_Testing/09-Testing_for_Weak_Cry
ptography/04-Testing_for_Weak_Encryption.html
CRE-ID: 273-300. (In case a segment links to multiple CRE's, multiple entries can be specified, or the CRE-ID's can be enumerated in the
CRE-ID field. For example: CRE-ID: 273-300, 251-823)
Link Type (optional, default is DTA): DTA (others are: SAM=same, SIM=similar, IPO = is part of)
```



