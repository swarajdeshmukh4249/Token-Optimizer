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
   choose this `extension/` folder.
3. Open chatgpt.com or claude.ai and paste a screenshot (⌘⇧⌃4 on a Mac copies one).

Toggle it off from the toolbar popup to show the "before" cost; the badge still
shows what the full screenshot costs. The popup also works on its own as a backup:
paste an image into it and download the optimized images.
