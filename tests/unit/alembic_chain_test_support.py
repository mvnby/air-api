from alembic.script import ScriptDirectory


def assert_revision_in_single_head_chain(
    script: ScriptDirectory,
    revision: str,
) -> str:
    heads = script.get_heads()
    assert len(heads) == 1
    head = heads[0]
    ancestry = {
        item.revision
        for item in script.walk_revisions(base="base", head=head)
    }
    assert revision in ancestry
    return head
