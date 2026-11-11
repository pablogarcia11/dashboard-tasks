from core.views import visible_git


def act(source, kind, repo=""):
    return {"source": source, "kind": kind, "extra": {"repo": repo} if repo else {}}


def test_visible_git_oculta_repo_entero_o_solo_wip():
    items = [act("git", "commit", "airisk-api"), act("git", "wip", "airisk-api"),
             act("git", "commit", "millie/apiREST"), act("git", "wip", "millie/apiREST"),
             act("git", "wip", "ibh/ibh-api"), act("notion", "note")]
    settings = {"millie/apiREST": {"visible": False, "show_wip": True},
                "ibh/ibh-api": {"visible": True, "show_wip": False}}
    kept = [(a["kind"], a["extra"].get("repo")) for a in visible_git(items, settings)]
    assert kept == [("commit", "airisk-api"), ("wip", "airisk-api"), ("note", None)]
