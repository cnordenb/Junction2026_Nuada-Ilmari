# Suggestion: project, roles and plan

Hostinger challenge, Junction 2026. Team of four. Deadline **Sunday 2026-11-15 10:00 EET** (about 36 hours from when this was written, Friday 21:30).

## 1. What to build

**"Name the technique" as the core, with a small "Trust the source" add-on if time allows.**

A web tool where anyone pastes text (or a URL) and gets:

- the manipulation techniques found (loaded language, fear appeal, whataboutism, fabricated authority, ...),
- the exact quoted passage for each one, highlighted in the text,
- a plain-language explanation of why that passage is manipulative,
- a confidence level, and an explicit **"no manipulation found"** or **"not sure"** outcome.

Plus a public **"How accurate is this?"** page showing precision, false-positive rate and the worst mistakes we found.

### Why this direction

| Reason | Detail |
|---|---|
| Matches what judges say they score | "Strength and honesty of detection logic, including false positives" over front-end polish. A measured, self-critical classifier fits exactly. |
| No data-access problem | Works on pasted text. "Spot the swarm" needs social-network data we do not have; "Clean the traffic" needs realistic labelled server logs. |
| Fits the resources | LLM calls through Hostinger AI Router; a small API and page on the VPS. No GPU or model training needed. |
| A non-technical member can own a critical part | The labelled test set and false-positive review are the heart of the score, and they need careful reading, not code. |
| Demo is instantly understandable | Paste a text, see highlighted passages with explanations. |

### What makes it honest rather than a demo

1. **Evidence must be a real quote.** The backend rejects any finding whose quoted passage does not appear word for word in the input. This removes invented findings.
2. **Abstaining is allowed.** Below a confidence threshold the tool says "not sure" instead of accusing.
3. **Hard negatives in the test set.** Neutral news, emotional but honest opinion pieces, satire, and quoted propaganda inside a report about it. These are where false positives come from.
4. **Published numbers.** Precision, recall and false-positive rate per technique, computed by a script anyone can rerun, shown on the live site together with known failure cases.
5. **Verdict is about the text, not the author.** The tool says "this passage uses a fear appeal", never "this is propaganda" or "this person is a bad actor".

## 2. Architecture (keep it small)

- **Backend:** Python FastAPI, one main endpoint `POST /analyze` returning JSON (techniques, quotes, explanations, confidence). This also satisfies the "API" form of the challenge.
- **Detection:** LLM through Hostinger AI Router with a fixed technique list and structured output, then quote verification and confidence thresholding in our own code.
- **Front end:** one page with a text box, highlighted result and the accuracy page. Plain HTML/JS served by the backend, or Hostinger AI Builder for the landing page.
- **Evaluation:** `eval/` folder with the labelled test set (CSV or JSON) and a script that outputs the metrics file the accuracy page reads.
- **Deploy:** Docker on the Hostinger VPS, free domain, HTTPS. **Deploy a "hello world" tonight** so the public URL exists from hour one.

Possible labelled data to bootstrap the test set: the SemEval-2020 Task 11 propaganda techniques corpus (news articles annotated with 14 techniques). Check access and licence before relying on it; our own hand-labelled set is still needed for the hard negatives.

## 3. Roles

| Role | Owner | Responsibility |
|---|---|---|
| Detection lead | technical member A | Prompt, technique list, quote verification, thresholds, model choice |
| Backend and deploy lead | technical member B | FastAPI, Docker, VPS, domain, HTTPS, rate limiting, uptime |
| Front end and evaluation tooling | technical member C | Result page, highlighting, accuracy page, evaluation script |
| **Evaluation and story lead** | non-technical member | See below |

### The non-technical team member: Evaluation and story lead

This is not a side role. The challenge is judged on honesty and false positives, and she owns both the evidence for that and how it is told.

Five tasks, shaped around her interest in UI/UX and diagrams:

1. **Design the result screen** (Saturday morning, needed first). Wireframe the main page in Figma or on paper: text box, highlighted passages, the explanation card for each technique, the confidence indicator, and the three outcomes "techniques found", "nothing found" and "not sure". The key UX question is hers to answer: how do we show a finding without it reading as an accusation? Hand the wireframe to the front-end owner by Saturday 11:00.
2. **Draw the "how it works" diagram** (Saturday midday). One clear flow diagram: text in, model proposes findings, quote check rejects anything not literally in the text, confidence threshold, verdict or "not sure". It goes on the live site and into the pitch, and it is how judges will understand our false-positive handling in ten seconds.
3. **Write the technique cards** (Saturday midday to afternoon). For each of the 6 to 8 techniques: a short name, a one or two sentence plain-language definition, one example, and a colour or icon used for highlighting. The wording is used both in the prompt and in what users read.
4. **Usability and false-positive testing** (Saturday afternoon to evening). Run 30 to 50 real texts through the live tool, including tricky clean ones (satire, emotional but honest opinion, news quoting propaganda). Log in a shared sheet every wrong verdict and every explanation a normal reader would not understand. Hand the worst to the detection lead, and pick 3 to 5 honest failures for the accuracy page.
5. **Design the accuracy page and the pitch** (Saturday evening to Sunday morning). Lay out the "How accurate is this?" page so precision and false-positive rate are readable by a non-expert (simple chart or table, sample size, failure examples). Build the 2 to 3 minute pitch slides from the diagram and screenshots, and choose the demo texts: one clear hit, one clean text that correctly passes, one admitted miss.

Tasks dropped from her list and to be shared by the three technical members: building the bulk of the labelled test set, mentor liaison, and the submission text.

**Tools she needs:** Figma (or similar), a diagram tool, a shared spreadsheet, the live URL, a slide tool. Nothing to install.

## 4. Timeline

| When | Milestone |
|---|---|
| Fri evening | Agree on scope and technique list (6 to 8 techniques, not 14). VPS up, "hello world" on public URL. Test set started. |
| Sat 10:00 | First end-to-end version live: paste text, get JSON verdict. First 50 labelled texts. |
| Sat 13:00 | Hostinger talk (one person attends). |
| Sat 16:00 | Highlighting UI live. Evaluation script produces first numbers. First false-positive review round. |
| Sat 22:00 | **Feature freeze.** Accuracy page live with real numbers. Only fixes after this. |
| Sun 07:00 | Final evaluation run, numbers frozen, pitch rehearsal, submission text ready. |
| Sun 09:00 | Submit. Keep the last hour as buffer. |
| Sun 10:00 | Deadline. |

## 5. Risks

- **Scope creep.** Combining several directions is tempting; one direction done with real numbers beats three shallow ones. The "Trust the source" add-on (domain age for a pasted URL) only starts if everything else is live by Saturday 16:00.
- **AI Router credits.** Shared balance. Cache results for the test set, use a cheaper model for development runs, and add rate limiting on the public endpoint.
- **Small test set.** 100 to 150 texts give rough numbers. Say so on the accuracy page, with the sample size.
- **Live demo failure.** Keep a few cached results so the page works even if the model call is slow.

## 6. Links

From `materials.md` (added 2026-11-14; none of these have been opened or checked):

- TRACE-Bot repository: https://github.com/forthgoer1/TRACE-Bot
- oc-botwatch (OpenCitations): https://awesome.ecosyste.ms/projects/github.com%2Fopencitations%2Foc-botwatch
- Research paper on sota2.com: https://www.sota2.com/research/paper/69cf49bf0636e5bf4afcdbf3
- AIUniti Signal (product): https://www.aiuniti.com/products/signal/
- AIUniti: what is coordinated inauthentic behaviour: https://www.aiuniti.com/blog-post/what-is-coordinated-inauthentic-behaviour/
- Xpoz technical guide to detecting coordinated inauthentic behaviour: https://www.xpoz.ai/blog/guides/detecting-coordinated-inauthentic-behavior-technical-guide/

Links from the challenge brief:

- Hostinger Connector docs: https://docs.hostinger.com/hostinger-connector
- Hostinger API reference: https://developers.hostinger.com
- Hostinger MCP server (open source): https://github.com/hostinger/api-mcp-server
- Hostinger help channel: link shared at kick-off and at the booth (not yet recorded here)
