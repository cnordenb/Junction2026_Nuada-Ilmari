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

**Tasks, in priority order**

1. **Build the test set** (Friday night to Saturday midday). Collect about 100 to 150 short texts in a shared spreadsheet: roughly half with a clear manipulation technique, half clean. Columns: text, source link, technique (or "none"), the exact passage, a note. Deliberately include the tricky clean ones: emotional but honest writing, satire, news that quotes propaganda.
2. **Write the technique definitions** in plain language, one or two sentences each plus one example. These go straight into both the prompt and the user-facing explanations, so her wording is what users read.
3. **False-positive review** (Saturday afternoon onward). Run texts through the live tool, record every wrong or doubtful verdict in the sheet, and hand the worst ones to the detection lead. Repeat after each improvement. Pick 3 to 5 honest failure examples for the accuracy page.
4. **Judge the explanations.** Would a normal reader understand why this is manipulative? Rewrite unclear ones and feed the style back.
5. **Pitch and demo.** Write the 2 to 3 minute story, choose the demo texts (one obvious hit, one clean text that correctly passes, one admitted miss), prepare slides, and rehearse with the team Sunday morning.
6. **Mentor liaison.** Visit the Hostinger booth early Saturday with our plan and ask what they want to see; attend the Saturday 13:00 talk and bring back anything relevant.
7. **Submission.** Own the Junction submission text, screenshots and the final check that the public URL works from a phone on mobile data.
8. Optional: build the landing page in Hostinger AI Builder (no code needed).

**Tools she needs:** a shared spreadsheet, the live URL, a slide tool. Nothing to install.

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

`materials.md` was empty when this was written, so there were no links to take from it. If it was meant to have content, save the file and this section can be updated. Links from the challenge brief:

- Hostinger Connector docs: https://docs.hostinger.com/hostinger-connector
- Hostinger API reference: https://developers.hostinger.com
- Hostinger MCP server (open source): https://github.com/hostinger/api-mcp-server
- Hostinger help channel: link shared at kick-off and at the booth (not yet recorded here)
