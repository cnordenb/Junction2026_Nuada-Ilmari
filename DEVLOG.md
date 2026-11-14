# DEVLOG

## 2026-11-13

**21:26:26** Read CLAUDE.md (Hostinger challenge brief). `materials.md` exists but is empty, so no links could be taken from it.

**21:30:00** Created `suggestion.md` with a proposed project, roles and timeline.
- Decision (proposed, not yet agreed by the team): build "Name the technique" (explainable manipulation-technique classifier for pasted text) with a public accuracy page; "Trust the source" only as an optional add-on.
- Decision (proposed): non-technical team member takes the role of evaluation and story lead (test set, technique definitions, false-positive review, pitch, mentor liaison, submission).
- Question: was `materials.md` meant to contain links? It needs to be saved or filled in.
- Question: is the SemEval-2020 Task 11 corpus accessible and licensed for our use? Not verified.
- Deadline noted: Sunday 2026-11-15 10:00 EET.

## 2026-11-14

**10:29:29** Updated `suggestion.md`: replaced the non-technical member's task list with five tasks built around UI/UX and diagrams (result-screen wireframe, how-it-works diagram, technique cards, usability and false-positive testing, accuracy page and pitch).
- Decision (proposed): bulk test-set labelling, mentor liaison and submission text move to the three technical members.
- Question: who among the technical members owns the labelled test set now?

**11:31:34** New idea from the team: example-based detector (user enters five posts, system extracts common signs and scans a larger dataset). Feedback given in chat, nothing built.
- Proposed implementation: LLM extracts explicit signs from the five examples contrasted with a background sample; embedding similarity ranks the dataset; LLM checks top candidates against the signs with quoted evidence; user confirm/reject loop.
- Question: does this replace 'Name the technique' or not? Team must choose one today.
- Question: which dataset to scan and evaluate on? Candidate: FiveThirtyEight Russian troll tweets mixed with ordinary tweets (not verified).

**11:33:26** Created `brainstorm.md` with the example-based detector idea, its analysis, a possible implementation and a comparison with 'Name the technique'.

**11:34:45** Added to `brainstorm.md`: visitor origin and VPN detection with origin-based restrictions (GeoIP, ASN, Tor and VPN lists, signal mismatches; firewall, nginx, app middleware and softer responses; analysis of false positives and privacy).
- Question: standalone tool, or a signal inside another idea?
- Not verified: licences and freshness of the free GeoIP and VPN lists.
