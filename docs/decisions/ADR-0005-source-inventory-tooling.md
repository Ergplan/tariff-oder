# ADR-0005 Inventory tooling for Milestone 1

Status: accepted

## Decision
PyMuPDF (`pymupdf`, version recorded on every source as `inventory_tool_version`) performs
the per-page inventory: text-layer chars, declared page labels, rotation, size, image and
drawing counts, font embedding, encryption and tagging.  `pypdf` is installed as the
secondary reader for Milestone 2 consensus but is not used yet.  Docling (primary table
reader), a secondary geometry reader (pdfplumber) and OCR engines are Milestone 2 decisions
recorded when they are measured on real pages.

## Why
PyMuPDF is fast on 400–600 page files, exposes drawing operators (needed to detect
vector-only tables in the KERC order) and page labels, and ships manylinux wheels.
