---
name: feature
description: Work through a Boster GitHub issue end to end - understand, clarify, plan, test first, implement, verify, self-review, wrap up. Run as /feature <issue number>.
argument-hint: <issue number>
disable-model-invocation: true
---

Work on GitHub issue #$ARGUMENTS in this order. Do not skip a step; say which step you are on.

## 1. Understand
- `gh issue view $ARGUMENTS` (with comments).
- Read the spec / README sections the issue references, and the code and tests it will touch.

## 2. Clarify (stop here until answered)
- Write the requirements as you understand them, as a short numbered list of acceptance criteria.
- List open questions and the assumptions you would otherwise make.
- Ask the user about anything that changes behaviour or a domain rule, using multiple-choice questions where possible. Don't ask what the spec, README or code already answers.
- If nothing is unclear, say so and continue.

## 3. Plan (wait for approval)
- Files to change, tests to write (one or more per acceptance criterion), and how you will verify UI changes.
- If the plan is bigger than one sitting, propose splitting it into smaller issues.

## 4. Build test first
For each acceptance criterion:
1. Write the test. Run it and confirm it fails for the expected reason (paste the failure line).
2. Write the minimal code to make it pass. Run it.
3. Refactor with the tests green.

Frontend has no test runner: keep logic in testable backend code where it belongs, and verify the UI in step 5.

## 5. Verify
- Backend: full `pytest -q`. Frontend: `npm run lint`, `npx tsc -b`, `npm run build`.
- UI changes: run `npm run dev` and check the real flow in the browser (Claude in Chrome if available), including empty/missing-data states ("Saknas").
- Check the result against each acceptance criterion from step 2.

## 6. Self-review
- Run the `code-review` skill on the diff. Fix real findings; explain any you reject.
- Check the CLAUDE.md rules: no estimated values, provenance kept, Swedish UI / English code.

## 7. Wrap up
- Update the README (status table, "What it does today") if behaviour changed.
- Propose a commit message ending in `Fixes #$ARGUMENTS`. Don't commit or push unless the user says so.
- Report: what changed, how each acceptance criterion was verified, what was **not** verified, and proposed follow-up issues.
