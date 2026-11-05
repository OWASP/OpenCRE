# The Librarian (Smart Content Mapping): My GSoC 2026 with OWASP OpenCRE (Module C)

*How OpenCRE's decision layer got built, measured, and shipped, and why the most valuable number in it is the one that says "I don't know."*

*Originally published on [Medium](https://medium.com/@prateek23022004/the-librarian-smart-content-mapping-my-gsoc-2026-with-owasp-opencre-module-c-8db874d46bab).*

Security knowledge is only useful if you can trust it. [OpenCRE](https://github.com/OWASP/OpenCRE) is OWASP's answer to one of the most tedious problems in security engineering: cross-standard traceability. If you need to know how an ASVS requirement maps to NIST 800-53, or how a PCI-DSS control connects to a WSTG test case, OpenCRE does that work in seconds instead of hours. It is a knowledge graph that links dozens of security standards into one navigable structure.

But knowledge graphs go stale. Cheat sheets get updated, new standard versions land, guidance evolves. And when the mappings fall behind, something subtle and serious happens: a practitioner follows one outdated link, gets one wrong answer, and loses confidence in the entire graph. Not that one entry. The whole thing.

This is the story of my Google Summer of Code 2026, where I built Module C of the OWASP Integrated Ecosystem: **The Librarian**, the component that decides what every incoming piece of security content means, and, more importantly, decides when it should not decide at all.

## How it started

I did not arrive at this project with a plan. I arrived with a pull request.

I had been contributing to OpenCRE since November 2025, across Gap Analysis, MyOpenCRE, parsers, the API, chatbot reliability, and CI. By the time I raised [#718](https://github.com/OWASP/OpenCRE/pull/718) and [#719](https://github.com/OWASP/OpenCRE/pull/719) against [issue #471](https://github.com/OWASP/OpenCRE/issues/471), I had 42 merged PRs and a decent mental model of how everything connected.

I thought #471 was a scoped fix. Then I got on a call with my mentors, Spyros Gasteratos, founder of Smithy Security and primary maintainer of OpenCRE, and Rob van der Veer from Software Improvement Group. They are the kind of mentors who do not just review your code. They ask why you made the decisions you made, and then they ask why again. What started as a discussion about two stacked PRs became a conversation about what OpenCRE actually needed. Not a fix for one issue. A decision layer: a component that could sit between incoming content and the knowledge graph and make a judgment call on every single section. Is this safe to auto-link, or does a human need to see it first?

That is what good mentorship looks like. Not direction. Expansion.

## The problem with a simple lookup

Before the Librarian, OpenCRE mapped incoming content with a function that found the closest CRE node by vector similarity and returned an ID or nothing. Useful as a lookup. Not enough for a living graph.

It could not tell you how confident it was. It could not catch a negation, so it scored "DO NOT use MD5" and "use MD5" as nearly identical, because the surrounding words are the same. And it could not route uncertain cases to a human. It either mapped or it did not, with no middle ground.

That middle ground is exactly where trust lives. The Librarian was built to own it.

## The shape of the machine

The OWASP Integrated Ecosystem is a pipeline of four modules, each built by a different contributor. Module A harvests new and changed content from OWASP repositories. Module B filters the noise and keeps security knowledge. Module C, my module, decides what each surviving chunk means. Module D puts a human in front of whatever C could not decide alone.

C's whole job is deciding when not to decide. A wrong link pollutes a graph that practitioners read as truth. Sending everything to a human defeats the automation. All of the value lives in the boundary between those two, and that boundary is where I spent my summer.

The most important design decision in the Librarian is not the threshold value. It is the direction of the default. When the system is uncertain, it routes to human review. Always. A low-confidence case never auto-links, and a risky mapping never reaches the graph without a person seeing it first, along with the score, the reasoning, and the evidence that explains what the system was thinking when it asked for help.

## Proving it before building it

Before writing a single line of production code, I ran a pre-coding experiment on real OpenCRE data with production Gemini embeddings. The question was simple: does the architecture actually work on this corpus, or does it only work in a diagram?

Two findings shaped everything after. First, retrieval was strong enough to build on. Second, adding a cross-encoder dropped overall top-1 accuracy slightly, from 0.920 to 0.820 on that early 50-item run, while handling the hard cases, negations especially, dramatically better. That trade was expected and intentional: the cross-encoder is more conservative, and for a system that should never silently make a wrong mapping, conservative is correct. It also planted a flag I would come back to in week 8, when the same tension between overall accuracy and hard-case handling returned at full scale.

The experiment felt like confirmation that the main technical risk was already reduced, and that the remaining work was engineering, testing, and integration. Which is exactly the right place to be before you start building.

## Eight stages, eight merges

Every stage of the Librarian landed as its own reviewed and merged pull request into OpenCRE's main branch. The contracts, config, and a 319-row hand-labelled golden dataset came first ([#922](https://github.com/OWASP/OpenCRE/pull/922)), because you cannot claim a decision system works without something to measure it against. Then the input boundary ([#925](https://github.com/OWASP/OpenCRE/pull/925)), candidate retrieval over the existing pgvector embeddings ([#937](https://github.com/OWASP/OpenCRE/pull/937)), the cross-encoder reranker ([#957](https://github.com/OWASP/OpenCRE/pull/957)), confidence calibration with an ECE gate ([#974](https://github.com/OWASP/OpenCRE/pull/974)), the decision engine and the pipeline glue ([#990](https://github.com/OWASP/OpenCRE/pull/990), [#991](https://github.com/OWASP/OpenCRE/pull/991)), and finally the live integration that made all of it real ([#1011](https://github.com/OWASP/OpenCRE/pull/1011)). A companion PR carried the package docs, the final metrics, and the CI regression gate ([#1012](https://github.com/OWASP/OpenCRE/pull/1012)); its content landed through [#1011](https://github.com/OWASP/OpenCRE/pull/1011), and that regression gate now runs on every pull request touching the Librarian.

The flow through those stages is simple to state. A chunk that explicitly cites a CRE id resolves deterministically, with no ML in the path at all. Everything else goes through retrieval, which pulls the top candidates from the graph, then reranking, which reads the chunk and each candidate together rather than separately, then calibration, which turns raw scores into confidence numbers that mean what they say. The decision engine applies one threshold: score at least 0.80 and the chunk auto-links, anything less goes to the human review queue with its candidates and its full audit trail attached.

Behind those merges sit 247 tests, and every one of them is hermetic. The whole suite runs in under four seconds with no database, no API key, and no model download, because every ML component sits behind a seam. The retriever takes an embedding function, the reranker takes a scoring function, the engine takes a guard. Live components and test stubs are interchangeable. That one early decision paid for itself every single week, because it meant every reviewer could run everything.

## The week with no code

Week 7 shipped zero lines and might have been the most useful week of the summer. I swept the auto-link threshold across all 319 golden chunks to see what each setting actually buys.

At the shipped threshold of 0.80, the system auto-links 172 chunks at 96.5 percent precision, with six wrong. Drop the bar to 0.70 and you automate thirty more chunks, and wrong links go from six to fourteen. A bad link committed into a graph that other tools consume as ground truth costs far more than one extra human glance. We held at 0.80.

The sweep also exposed a ceiling. Thresholding can raise *precision* by abstaining (96.5% auto-link precision here versus 75% top-1 ranking accuracy), but it cannot make the underlying ranker place the right CRE first more often. The review queue could not be shrunk from the threshold side at all. That finding set up the hardest part of the summer.

## The number I missed

The plan targeted 90 percent top-1 ranking accuracy. The shipped number is 75. I want to be precise about why, because the honest answer turned out to be more useful than any of my attempts to fix it.

I tried thirteen separate reranker levers: model swaps, prompt shapes, score fusion, candidate-pool changes. All thirteen regressed. The cross-encoder as shipped actually scores net minus seven against plain cosine similarity on the same shortlist. The root cause is not the model. It is the corpus: 427 of the 428 CREs have empty description fields. A cross-encoder scores a query against a document, and when the document side is effectively a bare title, there is nothing to cross-attend to. Retrieval still reaches 98 percent recall over that same thin corpus, which localises the problem exactly. The information needed to rank within a shortlist is simply not there to be read. The path to 90 percent runs through populating CRE descriptions, not through a better reranker.

There is a version that gets closer. Gating the reranker to fire only where it helps reached 250 of 319 against the shipped 238. It is deliberately unshipped. It needs held-out validation, but there was no time to do that honestly, and shipping it on in-sample numbers would be exactly the kind of quiet dishonesty this project spent three separate fixes eliminating elsewhere.

Meanwhile, the number I trust most: review recall is five out of five. Every chunk that should reach a human does. The engine never once wrongly auto-linked something that needed review. For a gate whose failure mode is polluting shared truth, that is the number that matters. Failing safe is not a slogan you put in a design doc. It is a measurement, and this one held.

## Going live

Week 8 made the handoff real. C now drains Module B's knowledge_queue, decides every row, writes each decision to decision_queue, the table Module D will read, and only then marks the source rows consumed. Consumption is gated on persistence, so a crash can never silently destroy a chunk. B will not re-offer a row C claimed to have finished, so C is not allowed to claim it finished anything until the decision is durably somewhere.

Integration found real bugs, the way integration always does. C originally read only B's KNOWLEDGE label and stranded the UNCERTAIN rows. Those are chunks B was unsure about classifying, not chunks it judged worthless. Module B's owner caught it, and C now reads both labels and records which one each decision came from.

The reviewing did not stop at the merge. Manshu, who built Module B, later [filed an issue](https://github.com/OWASP/OpenCRE/issues/1025) pointing out that C read the shared queue without row locking. Harmless with today's single consumer, unsafe the day anyone runs two. I verified his claim against the code. He was right. [The fix](https://github.com/OWASP/OpenCRE/pull/1030) (now on `main`) adds opt-in row claiming that refuses to run on a database that cannot honour the lock, rather than degrading silently. SQLite drops the locking clause without an error, and an unlocked batch handed to a caller who asked for a locked one is the kind of failure that surfaces weeks later, far from its cause. Then the automated reviewer caught a genuine transaction leak in my fix: dry runs were taking locks they never released. Two modules reviewing each other's assumptions, and a bot reviewing mine. That loop of claim, verify, counter-example, fix was the closest thing to real-world engineering this whole program offered.

## What I am handing over

Module C is complete as scoped, and its gaps are declared rather than hidden. The graph writer is deliberately blocked until a safety detector exists, because retiring a queue row is recoverable and committing a wrong edge into a trusted graph is not. The SafetyGuard seam is wired into the engine; the detection behind it is future work. The selective reranker is measured and waiting for held-out validation. Module D has a written contract and a populated decision queue waiting for it.

Everything is on main and reproducible from one command: the final report and full metrics live in [docs/gsoc_2026_module_c/](https://github.com/OWASP/OpenCRE/tree/main/docs/gsoc_2026_module_c) in the OpenCRE repository, and my complete contribution history is at [github.com/OWASP/OpenCRE](https://github.com/OWASP/OpenCRE/pulls?q=is%3Apr+author%3APRAteek-singHWY). The pull requests tell the story better than I can. Even this post lives there, committed alongside Module B's final blog in [#1040](https://github.com/OWASP/OpenCRE/pull/1040).

## What the summer actually taught me

Negative results are deliverables. Thirteen failed experiments plus one root cause is worth more to the next contributor than a lucky two-point gain. The most-cited artifact from my summer will probably be the finding that the corpus, not the model, is the bottleneck.

Contracts beat conversations. Every cross-module bug we hit lived in the gap between what someone assumed and what someone else wrote. Every fix shipped its documentation in the same pull request, because a contract that lags its code is just a rumor with a filename.

And the safe direction is a design choice you make once, early, and then defend. One hundred percent review recall at the cost of fifty-six percent auto-link recall is not a compromise. It is the point. Systems that guard shared truth should be able to say "I don't know" cheaply, and should say it by default.

## The people

None of this happens alone. Spyros Gasteratos mentored this project with questions rather than directions, and the bar he holds for what counts as verified changed how I work. Rob van der Veer's early questions shaped what the Librarian became before a line of it existed. Paola Garcia Cardenas and Parth Sohaney kept the reviews and the coordination moving through a busy final stretch. And Manshu made both our modules better by refusing to take either one's assumptions on faith. [His Module B writeups](https://manshusainishab.medium.com/) are worth your time, and his final chapter tells the other side of the [#1025](https://github.com/OWASP/OpenCRE/issues/1025) story.

GSoC 2026 is over. The pipeline is not. Module D needs building, the corpus needs descriptions, and I intend to be around for both.

Full contribution history: [github.com/OWASP/OpenCRE/commits?author=PRAteek-singHWY](https://github.com/OWASP/OpenCRE/commits?author=PRAteek-singHWY)
