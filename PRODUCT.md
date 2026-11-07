# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Analysts and budget-meeting readers (Portugal, 2027 planning context) who need a clear national view of public spend mentioning GAFAM products in 2022–2026, plus a Leiria-district deep dive. They open a static HTML presentation (and `reports/leiria/`), not an interactive app.

## Product Purpose

`gafam_contratos` searches Portuguese public-procurement and grant sources for GAFAM product mentions, aggregates three distinct money channels (contrato assinado, pedido ao mercado, apoio aprovado), and writes a static report under `reports/` (`index.html`, `data.json`, CSVs) suitable for nginx.

Success: a reader can see year totals, breakdowns, keyword coverage, press links, sources, and methodological caveats without conflating the three channels.

## Positioning

Open data pipeline that keeps the three money channels separate and labels them in European Portuguese — not a vendor dashboard or a single summed “GAFAM spend” figure.

## Constraints

- European Portuguese copy only; Brazilian-form bans in tests (`você`, `contato`, `registro`, `usuário`, `gerenciando`).
- Labels that must remain: `contrato assinado`, `pedido ao mercado`, `apoio aprovado`, `Na imprensa`.
- CDN stack (no Node build): daisyui@5 CSS, `@tailwindcss/browser@4`, chart.js@4.
- Report must work as static files from `reports/`; chart data may be embedded in the HTML (current design).
- Visual world for the report surface: Swiss / Müller-Brockmann editorial Read mode; accent `#c59300`; paper/ink; flush-left; grotesque + mono.

## Stack

Python package `gafam_contratos` generates HTML/CSS/JS strings. Static CDN assets only for the report UI.

## Assumptions

- Inferred from README, pipeline tests, and the UI redesign brief (subagent; no live product interview). Marked for human confirmation if product scope widens beyond the static report.
