# NEAR Hub Studio (prototype)

An admin view for the dashboard: build a question from a query, a chart and its words, check it, and prepare it as a pull request.

**Status: a prototype, and a project of its own.** Nothing on the site links to it, and the site is complete without this folder. The warehouse is simulated here: a query returns the rows the site already holds for the table it reads, and the pull request step does not contact GitHub.

## How it loads

Open `site/index.html#studio`. The page fetches `studio.css`, then `studio.js`, the first time that address is opened, and not before. Where this folder is absent, `#studio` opens the home page.

| File | Holds |
|---|---|
| `studio.css` | The Studio's styles. The page places them between its own two style blocks, so its later rules keep the last word. |
| `studio.js` | The Studio's code. It runs after the page's own script, reads the page's questions, charts and helpers by name, and adds two views to it: `V.studio` (`#studio`) and `V.studioEdit` (`#studio-edit`). |

## What the page keeps for it

- The loader, `studioLoad`, beside `route()` in `site/index.html`.
- A few things the site uses too, so they stay in the page: the SQL highlighter (`sxHl`), the find field's styles and icon (`.sx-find`, `.sx-findw`, `SX_FIND`) and the text for screen readers alone (`.sx-vh`).
