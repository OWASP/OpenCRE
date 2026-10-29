# OpenCRE Beta: Tester Guide

Thanks for helping us test OpenCRE's **MCP server** and **chatbot**. About 30 minutes is plenty; more is welcome.

## Before you start

- **Access is limited to OWASP accounts.** Sign in with your **OWASP email address** via OAuth. Other accounts will be rejected.
- You will test two surfaces: the **chatbot** (web UI) and the **MCP server** (from your own AI client, e.g. Claude Desktop, Claude Code, Cursor).

## 1. Chatbot

1. Open **https://staging.opencre.org** and sign in with your OWASP email.
2. Ask the sample questions below.
3. After **every answer**, click 👍 or 👎 under it. This is the most useful signal we get. If you click 👎, a small box opens: type a few words on what was wrong and press Send (optional).

## 2. MCP

Add the OpenCRE server to your client. The endpoint is **https://staging.opencre.org/mcp** (Streamable HTTP).

Claude Code:

```bash
claude mcp add --transport http opencre https://staging.opencre.org/mcp
```

Claude Desktop / other clients: add a remote MCP server (custom connector) with the same URL.

On first use your client opens a browser window with the Google sign-in, the same as the chatbot. **Sign in with your OWASP email.** Other accounts are refused. If the sign-in loops or is refused, note the exact message and send it to us (see "Reporting").

Then ask your assistant the sample questions below and check that it calls the OpenCRE tools (`ask`, `owasp_meta_*`) rather than answering from memory. You can tell by the tool-call indicator in your client.

In Claude Code, run `/mcp`, pick **opencre** and choose **Authenticate** if it shows "needs authentication".

**Good to know**
- Answers can take **5 to 30 seconds**.
- Each account is limited to **5 questions per minute, 40 per hour and 150 per day**, shared between the chatbot and MCP. If you hit a limit the answer says so and when to retry. That's expected, not a bug.
- To rate an MCP answer, ask your assistant to call the `rate_answer` tool with the `answer_id` from the answer, and a thumbs up or down plus an optional short reason.

## What's covered today

**Security standards and CREs**
- Look up a CRE or standard section and see what it maps to.
- Map between standards (e.g. ASVS to NIST, CWE to ASVS).
- Search by topic or keyword across standards.

**OWASP community and logistics** (experimental)
- Chapters, events, projects, board history, membership pricing.
- Talk or speaker claims. We expect it to say "I can't verify that" instead of guessing.

### Sample questions

Standards:
- "Which CREs cover session management, and what do ASVS and NIST say about them?"
- "What does ASVS require for password storage? Cite the sections."
- "Map CWE-79 to the related ASVS requirements."

Community:
- "Is there an OWASP chapter in Athens? When is the next event?"
- "Who is on the OWASP board?"
- "How much does OWASP membership cost?"
- "List the flagship OWASP projects."

### What we want to find out

- Is the answer **correct**, and does it **cite** real sections or IDs?
- Does it **admit when it doesn't know**, rather than invent something?
- Does it route correctly? A standards question should not get a community answer, and the reverse.
- Is it **fast enough**, and does the MCP tool-calling feel natural in your client?
- Does sign-in work first time on both surfaces?

## Stretch goal

These are questions we don't cover well yet. We'd love to see how they fail:

- Multi-hop questions across standards ("Which controls satisfy both PCI DSS and ASVS for logging?")
- Questions about the **latest** versions or very recent changes to a standard
- Comparing standards by intent ("Which is better for LLM apps, AISVS or ML Top 10?")
- Compliance advice for a specific system or architecture you describe
- Vague, typo-ridden or multi-part questions
- Non-English questions
- Who is on the OWASP board by name, or mapping a CWE to ASVS requirements. Both are known weak spots, so tell us how they fail
- Questions mixing community and standards ("Who runs the project behind ASVS, and what changed in v5?")
- Anything you'd naturally ask OpenCRE that isn't listed here

## Reporting results

Pick whichever is easiest:

1. **👍 / 👎 in the chatbot** after each answer (or the `rate_answer` tool over MCP). This is the quickest way, and we read all of it.
2. **Email your results** to **spyros@sgaster.me**. Free-form is fine: questions asked, what you got, what you expected, screenshots. For MCP issues, mention your client and version.

For bugs (sign-in failures, errors, hangs), include the time (with timezone), the surface (chatbot or MCP), and the exact error text if there is one.

Thank you!
