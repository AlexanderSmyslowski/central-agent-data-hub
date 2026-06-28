# First-Run Test Protocol (current main)

A moderator playbook for running a structured first-run usability test of Agent
Data Hub with a real person.

The point of this test is **not** to walk someone through the product. It is to
watch a person carry the public README and Getting Started on their own and find
out where the public docs break down. You moderate the *test*, not the product.

The tester drives. You observe, take notes, and only intervene when the test can
no longer continue technically.

The spoken moderator lines below are kept in German because the test is run
verbally with a German-speaking tester. Everything else is in English to match
the rest of `docs/`.

---

## 0. What This Tests Against

This protocol tests the current `main` branch. It does **not** test a historical
release tag unless the moderator explicitly checks out that tag first.

The tester should rely only on the current public surface:

- Repo landing page: <https://github.com/AlexanderSmyslowski/central-agent-data-hub>
- [`README.md`](../README.md), section **Public Quickstart**
- [`docs/public/getting-started.md`](public/getting-started.md)

The moderator should know the expected path, but should not hand it to the
tester up front. The point is to learn whether the public docs can carry the
first run.

---

## 1. Goal Of The Test

Open with (spoken, German):

> Ich möchte prüfen, ob der aktuelle öffentliche Stand von Agent Data Hub für
> jemanden ohne Vorwissen verständlich und ausführbar ist. Bitte denke laut.
> Wenn etwas unklar ist, sag es einfach. Ich werde nicht erklären, sondern nur
> beobachten und mitschreiben. Es geht nicht darum, ob du etwas falsch machst.
> Es geht darum, ob die Anleitung gut genug ist.

Do **not** say things like:

- "ADH ist so und so gemeint."
- "Draft heißt ..."
- "Hub View ist ..."
- "Du musst jetzt ..."

If the tester asks what something means:

> Bitte mach so weiter, wie du es aus der Anleitung verstehst. Ich notiere die
> Stelle.

---

## 2. Preparation Before The Session

Check the *environment*, do not explain the *product*.

The tester needs:

- Git
- Python 3.11 or 3.12
- Docker / Docker Desktop (running)
- A terminal
- A browser
- Internet

Test in a fresh folder, not inside an existing checkout:

```bash
mkdir -p ~/adh-first-run-test
cd ~/adh-first-run-test
```

Optionally verify Docker up front:

```bash
docker --version
docker ps
```

If Docker is not running, that is a **setup blocker**. Do not score it as an ADH
defect, but write it down — it still shapes the run.

---

## 3. Test Mode

You sit next to the tester or watch over screen share. You have exactly three
jobs:

1. Record time and steps.
2. Write down unclear words and error messages **verbatim**.
3. Do not help while the tester is still making progress.

If the tester is fully stuck, ask only:

> Was würdest du als Nächstes versuchen?

If still nothing works, record:

> Blocker: Tester konnte ohne Erklärung nicht fortfahren.

Then you may stop the test or give one minimal technical unblock.

---

## 4. Tester Handout

Give this block to the tester.

````markdown
# Agent Data Hub First Run

Goal:
Start from the public GitHub page, use the README and Getting Started, and try
to understand and run the public demo path without extra explanation.

Please think out loud:
- What is clear?
- What is unclear?
- What would you do next?
- Which error message do you see?

You do not have to do anything perfectly. This test checks the instructions, not
you.

Start:
1. Open the GitHub page:
   https://github.com/AlexanderSmyslowski/central-agent-data-hub
2. Use the README and Getting Started.
3. Work in a fresh folder, not in an existing checkout.
4. Afterwards, explain in your own words what Agent Data Hub does.
````

---

## 5. Moderator Reference: Expected Current Main Public Path

This command sequence is for the moderator's reference. Do not give it to the
tester unless the run is already technically blocked and you decide to unblock
once.

The expected public first run from the current `main` README and Getting
Started is:

```bash
git clone https://github.com/AlexanderSmyslowski/central-agent-data-hub.git
cd central-agent-data-hub
scripts/first_run_demo.sh
```

The getting-started guide also documents a manual troubleshooting path, an
optional guided local operator setup (`agent-hub setup`), and a separate
Markdown export step (`.venv/bin/python -m agent_hub.cli export`). Do not push
the tester toward these. Let them find whichever path the docs lead them to,
and note which one they take.

---

## 6. Observation Sheet (for the moderator)

Create this file **locally, outside the repo** — it can contain tester PII and
run-specific notes that do not belong in version control:

```text
~/adh-first-run-observations/adh-main-first-run-observation-YYYY-MM-DD.md
```

Template:

````markdown
# ADH Current Main First-Run Observation

Date: YYYY-MM-DD

Tester:
- Background:
- OS:
- Python:
- Docker:
- Has heard of ADH before: yes/no

Environment:
- Fresh clone: yes/no
- Target branch: main
- Used README: yes/no
- Used Getting Started: yes/no
- Took guided `agent-hub setup` path: yes/no

## Timeline
Start time:
Steps:
1.
2.
3.
End time:

## Results
- Clone succeeded: yes/no
- scripts/first_run_demo.sh succeeded: yes/no
- Public demo check succeeded: yes/no
- Hub View started: yes/no
- Hub View opened in browser: yes/no
- Optional mobile preview URL found/opened: yes/no/not tested
- Found Project actions: yes/no
- Found Use ADH with an agent: yes/no
- Found Connect an agent: yes/no
- Prepared or inspected an agent handoff: yes/no
- Found Connect your agent: yes/no
- Understood Choose your agent: yes/no
- Found Connection verification: yes/no
- Understood Connection verification: yes/no
- Found Check handoff: yes/no
- Found the Codex setup card: yes/no
- Understood Codex setup target/preview/install: yes/no
- Understood Codex setup can be verified from repo-local AGENTS.md: yes/no
- Understood public demo Codex setup is dry-run only: yes/no/not applicable
- Understood Claude/Hermes/custom setup needs manual verification: yes/no
- Understood terminal fallback is temporary, not the normal daily path: yes/no
- Understood mobile preview is local read/orientation only: yes/no/not applicable

Moderator diagnostics if needed:
- script created `.venv`: yes/no/unknown
- script created `.env`: yes/no/unknown
- script started demo DB: yes/no/unknown
- script ran smoke check: yes/no/unknown
- script started Hub View: yes/no/unknown

## First friction
First unclear word or phrase:
> ...
First unclear command:
> ...
First wrong assumption:
> ...
First actual error:
```text
...
```
First place where tester wanted explanation:
> ...

## Concept understanding after the run
"What do you think Agent Data Hub does?"
> ...
"What do you think reviewed memory means?"
> ...
"What do you think a draft is?"
> ...
"What do you think Hub View is?"
> ...
"What do you think Connect an agent does?"
> ...
"What do you think Connection verification means?"
> ...
"What do you think the Codex setup card would change?"
> ...
"What can ADH verify automatically, and what still needs a manual check?"
> ...
"Why is the public demo install button disabled?"
> ...

## Safety / public-flow observations
- Any private/local maintainer traces visible: yes/no
- Any confusing public vs maintainer path: yes/no
- Any secrets/credentials exposed: yes/no
- Any unclear Docker/Postgres behavior: yes/no
- Did OKF/MCP distract from the first run: yes/no

## Improvement candidates
- ...

## Decision
Change docs now:
- yes/no
- what:
No change:
- why:
Needs second tester:
- yes/no
````

---

## 7. Standard Moderator Replies During The Test

When the tester asks "Was ist reviewed memory?":

> Bitte sag mir erst, was du aus der Anleitung heraus verstehst. Ich notiere die
> Stelle.

When the tester asks "Soll ich jetzt diesen Befehl ausführen?":

> Mach so weiter, wie du es aus der Anleitung ableiten würdest.

When the tester says "Ich komme nicht weiter.":

> Was würdest du als Nächstes versuchen?

When they are genuinely blocked after that:

> Okay, ich notiere das als Blocker. Wir stoppen hier oder ich gebe dir einen
> minimalen technischen Hinweis.

---

## 8. What To Watch Actively

These are the spots worth concentrated attention:

1. Does the tester understand ADH is a **technical preview**, not a finished
   product?
2. Does the tester understand it is about **reviewed project memory**?
3. Does the tester understand why there is a **public demo DB**?
4. Does the tester understand Hub View is **local**?
5. Does the tester understand Hub View is **not the operational source of truth**?
6. Does the tester understand **draft vs reviewed memory**?
7. Do **MCP** or **OKF** confuse the first run?
8. Is there **any maintainer-local trace** visible in the public path?
9. Do they get stuck on **Docker / Postgres**?
10. Is the command `scripts/first_run_demo.sh` clear?
11. Does **Project actions** make the main next steps visible?
12. Does **Use ADH with an agent** make it visible that reviewed ADH context
    is being handed to a chatbot or local agent?
13. Does **Connection verification** make it clear what ADH can check and what
    remains a manual/external check?
14. Does the tester understand that Codex setup writes a repo-local
    `AGENTS.md` block, not Hub memory?
15. Does the tester understand that the public demo shows a dry-run preview and
    does not install the demo block?
16. Does the tester understand that Claude/Hermes/custom agents need their own
    setup outside Hub View?
17. Does the tester understand that the terminal fallback is temporary?
18. If `scripts/first_run_demo.sh --mobile` is used, does the tester understand
    it is a local Wi-Fi preview and not a hosted app?

The current README deliberately frames Agent Data Hub as a local technical
preview, not a hosted product or finished end-user app. Anything the tester says
that contradicts that framing is a high-value observation.

---

## 9. When The Test Succeeds

The test succeeds if the tester, **without explanation**, can:

- clone the repo
- run `scripts/first_run_demo.sh`
- see the public demo check pass
- open Hub View
- find **Project actions**
- find **Use ADH with an agent**
- find **Connect an agent**
- understand that the agent handoff is reviewed ADH context being handed to a
  chatbot or local agent
- find **Connection verification**
- understand what ADH can verify automatically and what still needs a manual
  check
- find the Codex setup card
- understand whether the Codex setup can install or is only a public-demo
  preview/dry-run
- understand that terminal fallback is not the intended long-term daily path
- roughly explain that ADH manages reviewed project context for humans and
  agents

Individual terms being unclear is fine. The older granular steps — venv, pip
install, `.env`, demo DB start, smoke check, Hub View start — are moderator
diagnostics only.

---

## 10. When It Is A Real Blocker

Blocker:

- README points to a wrong command
- Getting Started contradicts README
- Public demo does not start
- Smoke test fails
- Hub View does not start
- Mobile preview claims to enable remote review or setup writes
- Tester needs maintainer knowledge to continue
- `.env` points at the wrong DB
- Private maintainer traces appear
- Drafts look like reviewed truth

Not a blocker (but still an observation):

- Tester takes longer
- Tester finds a term unfamiliar
- Tester asks what OKF or MCP is
- Docker was simply not started locally

---

## 11. After The Test

Do not change everything immediately. Sort first:

- **A. Reproducibility problem** — must be fixed before the next public mention.
- **B. Comprehension problem** — small docs correction.
- **C. Expectation problem** — sharpen README / release positioning.
- **D. Nice-to-have** — later.

Priority order:

1. Wrong commands
2. Missing setup information
3. Public/maintainer confusion
4. Draft/reviewed confusion
5. Overstated product assumptions
6. Terminology polish

---

## 12. Debrief Questions For The Tester

At the end, without correcting them:

- Was glaubst du, ist Agent Data Hub?
- Was würdest du damit machen?
- Was würdest du **nicht** damit machen?
- Welche Stelle war am unklarsten?
- Welcher Befehl war am unsichersten?
- Was hättest du früher wissen wollen?
- Hast du erkannt, wie ADH Kontext an eine KI oder einen Agenten übergibt?
- Hast du verstanden, was ADH bei der Agent-Verbindung prüfen kann und was
  nicht?
- Was wäre für dich der normale Weg: Chatbot, Codex, Claude, Hermes/custom oder
  Terminal fallback?
- Was klang nach Produktversprechen, obwohl es vielleicht nur Preview ist?

Only after their answers may you explain what ADH actually means.

---

## 13. Short Moderator Script

Start:

> Danke. Ich teste heute nicht dich, sondern die öffentliche Anleitung von Agent
> Data Hub. Bitte denke laut. Wenn etwas unklar ist, sag es. Ich werde nicht
> helfen, solange du weiterkommst, sondern nur notieren. Du startest bitte auf
> der GitHub-Seite und versuchst, die Public Demo und Hub View zum Laufen zu
> bringen.

During:

> Ich notiere das.
> Mach weiter so, wie du es aus der Anleitung verstehst.
> Was würdest du jetzt versuchen?

End:

> Danke. Bitte erklär mir jetzt in deinen Worten, was du glaubst, was Agent Data
> Hub macht.

---

## 14. Choosing The First Tester

Do not pick someone completely non-technical. Pick someone technical enough for
terminal, Git, Python, and Docker, but **without ADH prior knowledge**:

- a developer
- a technical operator
- an AI / Codex power user
- a technical founder

Not someone without terminal experience — otherwise you are testing Docker and
Python basics, not ADH.

---

## 15. Exit Criterion

After the test, a real observation note should exist containing:

- at least one genuine uncertainty
- at least one genuine tester explanation in their own words
- exact errors, if any occurred
- a clear decision: change / do not change / test again

Only then is the next ADH docs fix worth doing.
