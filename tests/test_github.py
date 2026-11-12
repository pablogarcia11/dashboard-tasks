import httpx

from collectors.github import GithubCollector, GithubError, error_message, pull_requests

ITEM = {"id": 7, "number": 42, "title": "feat: roles", "html_url": "https://github.com/org/api/pull/42",
        "repository_url": "https://api.github.com/repos/org/api", "updated_at": "2026-11-12T09:00:00Z",
        "draft": True, "user": {"login": "ana"}}


def test_pull_requests():
    [pr] = pull_requests([ITEM], "review", "2026-11-12")
    assert (pr.source, pr.kind, pr.external_id, pr.project, pr.work_date) == ("github", "review", "review:7", "org/api", "2026-11-12")
    assert pr.extra == {"repo": "org/api", "number": 42, "draft": True, "author": "ana", "updated": "2026-11-12T09:00:00Z"}


def test_collect_hace_las_dos_busquedas():
    seen = []
    def handler(request):
        seen.append(request.url.params["q"])
        return httpx.Response(200, json={"items": [ITEM] if "review-requested" in request.url.params["q"] else []})
    c = GithubCollector("t", http=httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler)))
    out = c.collect()
    assert len(out["review"]) == 1 and out["pr"] == []
    assert any("review-requested:@me" in q for q in seen) and any("author:@me" in q for q in seen)


def test_errores_con_el_paso_para_arreglarlo():
    c = GithubCollector("t", http=httpx.Client(base_url="https://api.github.com",
                                               transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    try:
        c.collect()
        assert False
    except GithubError as e:
        assert "GITHUB_TOKEN" in str(e)
    assert "SSO" in error_message(403, "Resource protected by organization SAML enforcement")
