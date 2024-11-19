# Contributing to OpenCRE

:+1::tada: First off, thanks for taking the time to contribute! :tada::+1:

The following is a set of guidelines for contributing. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

#### Table Of Contents

* [Code of Conduct](#code-of-conduct)

* [I don't want to read this whole thing, I just have a question!!!](#i-dont-want-to-read-this-whole-thing-i-just-have-a-question)

* [How Can I Contribute?](#how-can-i-contribute)
  * [How can I contribute a mapping or change the catalog of CREs?](#how-can-i-contribute-a-mapping-or-change-the-catalog-of-cres)
  * [Reporting Bugs](#reporting-bugs)
  * [Suggesting Enhancements](#suggesting-enhancements)
  * [Your First Code Contribution](#your-first-code-contribution)
  * [Pull Requests](#pull-requests)

* [Styleguides](#styleguides)
  * [Git Commit Messages](#git-commit-messages)
  

## Code of Conduct

This project and everyone participating in it is governed by the [OWASP Code of Conduct](https://owasp.org/www-policy/operational/code-of-conduct). By participating, you are expected to uphold this code.

## I don't want to read this whole thing I just have a question!!!

> **Note:** Please don't file an issue to ask a question.

You can reach us in the [OWASP Slack](https://owasp.org/slack/invite) at channel #project-cre

or send a message to rob.vanderveer@owasp.org

## How Can I Contribute?

The "Issues" page lists a number of features we would like to implement, we have tagged the ones we believe are easy to pick up with the tag `good first issue` and/or `beginner`. Alternatively you can contribute content (see below) or request features or mappings by opening an Issue.


### How can I contribute content (a standard mapping or changes to the CRE catalog)?

Adding a mapping to OpenCRE for a new standard X means that sections in X are each assigned to the corresponding ‘Common Requirement’ (or CRE number) at opencre.org.
For example, the section 613-Insufficien Session expiration in the CWE standard is mapped to CRE 065-782 Ensure session timeout (soft/hard).
The result is that when you go to the overview page of that requirement(CRE), users will see a link to CWE 613: https://www.opencre.org/cre/065-782

How to:
1. Get the OpenCRE standard mapping template spreadsheet
2. For every section in the standard, find the corresponding Common Requirement (CRE number) at OpenCRE and enter in that row the details of that section in the right columns:  name, id, and hyperlink 
3. In case you identify opportunities to add Common Requirements: add those to the spreadsheet
4. Send the mapping template file by creating a new github issue and add the file. That way, the community can see it, and we can use that issue to further communicate. Another option is to send the file to rob.vanderveer@owasp.org. You can also use that mail address for any questions.

ad. 1 
The mapping spreadsheet (Excel) can be obtained [here](https://github.com/OWASP/OpenCRE/raw/refs/heads/main/docs/CREmappingtemplate.xls).  
Note, it contains one example, where it links the CRE for development processes to a section in NIST 800-53.

ad.2

The spreadsheet shows the hierarchical organization of Common Requirements.
You can browse or search through it, to find a good match.
That same content can also be found in our explorer: https://zeljkoobrenovic.github.io/opencre-explorer/
From that page you can click on the common requirements to see to what standard sections it has been mapped, to perhaps give you a better idea.
We do not recommend to use an existing mapping from the standard to another standard that is already in OpenCRE (e.g. CWE). Typically, details get lost that way.
Note that we are developing an AI module to help create an initial mapping to a new standard, based on the text of that standard.

ad.3
Sometimes the new standard can have more detail in topics than OpenCRE has. For example, OpenCRE has the Common requirement of Automated Dynamic security testing and the new standard distinguishes applying DAST tools and applying IAST tools, than you may suggest two new Common Requirements as children of Automated Dynamic security testing and link each of them to the corresponding sections in the new standard. For that, you make two new rows below. As code for the requirements you don’t enter an XXX-XXX number, but you enter ‘NEW|Apply DAST tools’ where the | character separates the code from the name of the requirement.
In general, this will be rare.

ad.4
OpenCRE has an importing interface in case you run your own myOpenCRE, but for the public opencre.org we first perform some checks before we add a standard to it - hence the request to send the mapping to us in email.


### Reporting Bugs

When you are creating a bug report, please [include as many details as possible](#how-do-i-submit-a-good-bug-report). Fill out [the required template](https://github.com/common-requirement-enumeration/.github/blob/main/.github/ISSUE_TEMPLATE.md), the information it asks for helps us resolve issues faster.

> **Note:** If you find a **Closed** issue that seems like it is the same thing that you're experiencing, open a new issue and include a link to the original issue in the body of your new one.

#### How Do I Submit A (Good) Bug Report?

Bugs are tracked as [GitHub issues](https://guides.github.com/features/issues/). Create an issue and provide the following information by filling in [the template](https://github.com/common-requirement-enumeration/.github/blob/main/.github/ISSUE_TEMPLATE.md).

Explain the problem and include additional details to help maintainers reproduce the problem:

* **Use a clear and descriptive title** for the issue to identify the problem.
* **Describe the exact steps which reproduce the problem** in as many details as possible.
* **Provide specific examples to demonstrate the steps**. Include links to files or GitHub projects, or copy/pasteable snippets, which you use in those examples. If you're providing snippets in the issue, use [Markdown code blocks](https://help.github.com/articles/markdown-basics/#multiple-lines).
* **Describe the behavior you observed after following the steps** and point out what exactly is the problem with that behavior.
* **Explain which behavior you expected to see instead and why.**

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion, including completely new features and minor improvements to existing functionality. Following these guidelines helps maintainers and the community understand your suggestion :pencil: and find related suggestions :mag_right:.

When you are creating an enhancement suggestion, please [include as many details as possible](#how-do-i-submit-a-good-enhancement-suggestion). Fill in [the template](https://github.com/OWASP/OpenCRE/blob/main/docs/ISSUE_TEMPLATE.md), including the steps that you imagine you would take if the feature you're requesting existed.

#### How Do I Submit A (Good) Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](https://guides.github.com/features/issues/). Create an issue on that repository and provide the following information:

* **Use a clear and descriptive title** for the issue to identify the suggestion.
* **Provide a step-by-step description of the suggested enhancement** in as many details as possible.
* **Provide specific examples to demonstrate the steps**. Include copy/pasteable snippets which you use in those examples, as [Markdown code blocks](https://help.github.com/articles/markdown-basics/#multiple-lines).
* **Describe the current behavior** and **explain which behavior you expected to see instead** and why.
* **Explain why this enhancement would be useful**.

### Your First Code Contribution

Unsure where to begin contributing? You can start by looking through these `beginner`, `good first issue` and `help-wanted` issues:

* Beginner issues - issues which should only require a few lines of code, and a test or two.
* Good first issue - issues which should require more substantial changes but can be done in an afternoon or two.
* Help wanted issues - issues which should be a bit more involved than `beginner` issues.

#### Pull Requests

Each Pull Request should close a single ticket and only make changes necessary in order for this to be done. Please reference the relevant ticket in the Pull Request.
After you submit your pull request, verify that all [status checks](https://help.github.com/articles/about-status-checks/) are passing <details><summary>What if the status checks are failing?</summary>If a status check is failing, and you believe that the failure is unrelated to your change, please leave a comment on the pull request explaining why you believe the failure is unrelated. A maintainer will re-run the status check for you. If we conclude that the failure was a false positive, then we will open an issue to track that problem with our status check suite.</details>

## Styleguides

We use eslint and black to enforce style. `make lint` should fix most style problems.

### Git Commit Messages

* Use the present tense ("Add feature" not "Added feature")
* Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
* Limit the first line to 72 characters or less
* Reference issues and pull requests liberally after the first line
* When only changing documentation, include `[ci skip]` in the commit title.
