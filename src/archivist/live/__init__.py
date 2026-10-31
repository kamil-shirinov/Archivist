"""Live reading in the local app, for the demo video (P35).

    uv run python -m archivist.live

A local server that serves the review app (ui/) and adds a page picker limited to development pages,
a "Read live" action that runs the existing pipeline on the chosen page, a stream of events (one per
step and per model call) and a Replay mode that plays a cached read without spending (see server.py,
session.py, reader.py, events.py). The published site stays static (D12, D13): nothing here is
served by it, and the app offers a live read only where this server has told it it is.
"""
