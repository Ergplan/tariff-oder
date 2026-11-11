# DISCOM ARR Database (static site)

Ask about the revenue requirements of Indian DISCOMs in plain English. The page shows how it
read the question, the SQL it wrote (which you can edit), the answer, and for each row the page
of the order and the line as printed.

- `data/arr.sqlite`: the database, built by `tools/arrdb` (see its README). It is machine-read
  and not reviewed.
- `nl2sql.js`: the plain-English translator. It applies fixed rules (no model), so the same
  question always gives the same SQL, and it explains every part of the query it writes.
- `vocab.js`: the DISCOM names, states and latest year it uses, read from the database.
- `app.js`, `index.html`, `styles.css`: the page. SQLite runs in the browser through sql.js
  (cdnjs, version 1.10.3). There is no server and nothing is sent anywhere.

Tests: `node --test apps/arr-db/nl2sql.test.mjs` (Node 22+). They check the translator, and
check its answers against figures people read by hand from the same orders
(`packages/order-reproductions`).

Deployed as the Vercel project `arr-101` (root directory `apps/arr-db`), at
https://arr-101.vercel.app.
