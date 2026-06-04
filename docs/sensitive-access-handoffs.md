# Sensitive Access Handoffs

Agent Data Hub tracks project memory and operational boundaries. It does not
store protected access values.

Use this rule whenever work needs hosting, deployment, FTP, control-panel, or
production credentials.

## Core Rule

- Store in the Hub that protected access exists and when it is needed.
- Do not store the access value itself in Hub memory, Git, Obsidian, or repo
  prompts.
- Request a human-controlled secure handoff only at the moment the protected
  step must actually happen.

## Approved Pattern

1. Do the normal project work locally first.
2. Stop when the next step requires protected access.
3. Ask the Human Lead for a secure handoff outside the Hub, Git, and Obsidian,
   or ask the Human Lead to perform the protected action directly.
4. Complete the protected step only inside that approved handoff path.
5. Store back only the reviewed, non-sensitive result:
   what changed, which environment was touched, whether it succeeded, and what
   still needs review.

## CommCats

For `commcats-de`, Alfahosting upload access follows this rule.

- Agents should work from the local static source by default.
- Live upload happens only after explicit approval.
- If a new chat or agent session needs upload access, it should ask for a
  human secure handoff for the live upload step instead of searching the Hub or
  repo for credentials.

## If Access Is Missing

If no approved handoff is available:

- do not guess
- do not search old chats as if they were a credential vault
- do not store placeholder secrets in notes
- stop at the boundary and leave an open question or handoff note

That keeps the Hub useful as reviewed operational memory without turning it
into a secret store.
