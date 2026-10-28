"""Document types drafted by a model, tested by arithmetic, approved by a person (P21b).

    python -m archivist.templates.families     # which Treasury families to draft, by a fixed rule
    python -m archivist.templates.draft --family <name> --pages <ids>
    python -m archivist.templates.test --family <name>
    python -m archivist.templates.approve --family <name>   # for a person, interactive
    python -m archivist.templates.rediscover   # can the drafter find the ledger's own rules?

A draft is templates/<family>.yaml with status "draft": it validates like any template and is never
registered. The arithmetic test reads its sample pages through the pipeline's own steps and writes
templates/<family>.evidence.json; only the approval, which a person runs, makes it "approved", and
even then no run enables it until a run config names it (doctypes.from_config).
"""
