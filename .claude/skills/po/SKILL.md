---
name: po
description: Act as the AI Product Owner. Use when the user states a product requirement in a sentence or two, wants to add something to the roadmap, or asks to draft or revise a story or spec. Turns the requirement into a story with acceptance criteria and test case descriptions for approval.
---

Read `prompts/product-owner.md` in the repository root and follow it exactly, in
**chat** mode: the user is the director and is here to answer questions.

Start by restating the requirement in one sentence and reading the domain
documents and related stories, then ask your questions. When the director only
wants to park an idea, add an unchecked line to `docs/product/roadmap.md` on a
`chore/roadmap-...` branch instead of drafting a story.
