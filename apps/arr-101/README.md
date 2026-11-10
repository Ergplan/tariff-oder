# ARR 101

A ten-step guide to an electricity distribution licensee's ARR filing, worked through for a
**fictional** 150-consumer utility. Each step has plain words, questions with editable sample
answers, the live working, and what to watch out for.

- Every figure is invented and every norm is illustrative. It is a learning example, not a filing
  tool, and not regulatory advice.
- Static site: `index.html`, `styles.css`, `app.js`, `steps.js` (content), `calc.js` (arithmetic).
  No build step, no dependencies, no server. Answers are kept in the browser's local storage only.

## Run locally

    cd apps/arr-101 && python3 -m http.server 3200

## Test the arithmetic

    node --test apps/arr-101/calc.test.mjs

## Deploy on Vercel

Import the repository, set **Root Directory** to `apps/arr-101`, framework preset **Other**.
`vercel.json` turns off install and build; the folder is served as is.
