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

## 5. Verify (independent QA)
- Run full `pytest -q` yourself first, so QA doesn't start on a broken build.
- Hand off to the `qa` agent (`.claude/agents/qa.md`) with the Agent tool. Give it: the issue number, the numbered acceptance criteria from step 2 (with the owner's answers), the changed files, and what you already verified. Don't give it your reasoning or tell it what result to expect.
- Don't use the browser or edit files while it runs. Wait for its report.
- Act on the report: fix each real problem (backend fixes start with a failing test), then send the same agent a follow-up message to re-test what changed. Explain any finding you reject. Repeat until it passes or only unverifiable items remain.

## 6. Self-review
- Run the `code-review` skill on the diff. Fix real findings; explain any you reject.
- Check the CLAUDE.md rules: no estimated values, provenance kept, Swedish UI / English code.
- If a fix in this step changes behaviour, ask the `qa` agent to re-test the affected criteria.

## 7. Wrap up
- Update the README (status table, "What it does today") if behaviour changed.
- Propose a commit message ending in `Fixes #$ARGUMENTS`. Don't commit or push unless the user says so.
- Report: what changed, how each acceptance criterion was verified (including the QA agent's verdict), what was **not** verified, test data QA left in the browser, and proposed follow-up issues.
