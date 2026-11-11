"""ARR Network agents (see docs/arr-network/ARCHITECTURE.md).

The agents write to the database only through the application's ingest API
(docs/arr-network/INGEST.md).  Every reading keeps its order, page and the line as printed;
nothing here marks anything reviewed.
"""

__version__ = "0.1.0"
