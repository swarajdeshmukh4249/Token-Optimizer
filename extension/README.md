# TokenOpt browser extension

Paste a screenshot into ChatGPT or Claude.ai and TokenOpt sends the cheapest
equivalent instead, using the local engine (no API keys, nothing leaves your laptop
except what you send to the chat yourself).

- **New screen:** small overview + sharp crops of the detailed regions, if that is
  cheaper under the provider's image formula; otherwise the original goes through.
- **Same screen again:** only the changed regions (pHash scene check + per-patch diff,
  grouped with Union-Find), plus a one-line note telling the model where they go.
- **Duplicate:** no image at all, just the note.

Token numbers are **estimates** from the providers' published image formulas
(Anthropic `ceil(w*h/750)`; OpenAI GPT-4o `85 + 170 per 512 px tile`). Chat apps do
not report real counts.

## Run

1. Start the engine from the project root: `.venv/bin/python web/server.py`
2. Chrome → `chrome://extensions` → enable **Developer mode** → **Load unpacked** →
   choose this `extension/` folder (after code changes, press the reload arrow on its card).
3. Click the TokenOpt toolbar icon: the **side panel** opens next to the chat.
4. Open chatgpt.com or claude.ai, paste a screenshot (⌘⇧⌃4 copies one) and send a prompt.

## Side panel: the token ledger

Every prompt you send in that tab gets a card:

| line | how it is counted |
|---|---|
| Prompt text | OpenAI's o200k tokenizer via tiktoken on the local server: exact for ChatGPT, an estimate for Claude |
| Screenshots | full cost → what was actually sent (new screen / changes only / duplicate), provider image formula |
| Reply | the assistant's answer, counted once it stops streaming |
| Used | text + screenshots as sent + reply |
| Saved by TokenOpt | (text without our layout note + full screenshots + reply) − used |

The top card sums the tab's conversation. Switch TokenOpt **off** in the panel to record
"before" prompts (full screenshots go through), then **on** for the "after" prompts.
"Manual mode" opens the old popup as a page: paste an image, download the optimized files.

Limits: only screenshots pasted with ⌘V are tracked (not drag-and-drop or the upload
button); prompt/reply detection relies on the chat sites' current page structure.
