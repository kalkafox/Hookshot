"""The setup downloads from the server's own address when git.notrexed.dev gives no answer at all (builder/setup/setup.c
http_get). 2026-11-15: players kept seeing "The download server didn't answer (0)", through WARP and VPNs too: an antivirus's
web filter or a provider blocking notrexed.dev. The VPS serves the release files, the latest links and the API's latest release
on git.13.140.227.35.sslip.io itself, not through Cloudflare. Checked by source:

- every git.notrexed.dev request goes through http_get, which asks the same path on the other host when there was no answer
  (no status), and keeps asking it first for the rest of the run; an answer with an error status does not switch;
- 2026-11-26: a release link or API request that both VPS hosts fail (no answer, or a 5xx such as Cloudflare's 521 while the
  VPS's web server was down) is asked of the GitHub repository's releases, the same path there; a 404 and the like does not
  switch, and a GitHub failure leaves git.notrexed.dev's status for the message and the retries;
- no other code opens a connection itself (http_get_once is only called by http_get and http_get_vps).

python -I -B tests/test_setup_fallback_host.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def body(text, head):
    start = text.index(head)
    depth, i = 0, text.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start:i + 1]
        i += 1


def main():
    src = (ROOT / "builder/setup/setup.c").read_text(encoding="utf-8")
    assert 'static const char kMainHost[] = "https://git.notrexed.dev/";' in src
    assert 'static const char kFallbackHost[] = "https://git.13.140.227.35.sslip.io/";' in src
    vps = body(src, "static int http_get_vps(")
    for need in ("if (ok || g_http_status) return ok;", "g_fallback = !fallback;"):
        assert need in vps, "http_get_vps: " + need
    get = body(src, "static int http_get(const char *url8")
    for need in ("if (strncmp(url8, kMainHost, main_n)) return http_get_once(url8, sink, user, expect, accept);",
                 'snprintf(other, sizeof other, "%s%s", kFallbackHost, url8 + main_n);',
                 "int ok = http_get_vps(url8, other, sink, user, expect, accept);",
                 "if (ok || !mirrored || g_github || (g_http_status && g_http_status < 500)) return ok;",
                 "ok = http_get_once(gh, sink, user, expect, accept);",
                 "else g_http_status = vps_status, g_http_error = vps_error;"):
        assert need in get, "http_get: " + need
    for need in ('static const char kRepoPath[] = "Hookshot/Hookshot/releases/";',
                 'static const char kApiPath[] = "api/v1/repos/Hookshot/Hookshot/releases/";',
                 'static const char kGitHubRepo[] = "https://github.com/ItsNotRexed/Hookshot/releases/";',
                 'static const char kGitHubApi[] = "https://api.github.com/repos/ItsNotRexed/Hookshot/releases/";'):
        assert need in src, need
    asset = src[src.index("static int asset_from_json("):src.index("static int api_asset_url(")]
    for need in ("!strncmp(out, kGitHubRepo, sizeof kGitHubRepo - 1)", "(!next || url < next)"):
        assert need in asset, "asset_from_json (GitHub's asset links, past its uploader object): " + need
    once = body(src, "static int http_get_once(")
    assert "g_http_error = 0, g_http_status = 0;" in once, "a request's status is its own"
    calls = [m.start() for m in re.finditer(r"\bhttp_get_once\(", src)]
    inside = [c for c in calls if any(src.index(f) <= c < src.index(f) + len(f) for f in (get, vps))]
    assert len(calls) - len(inside) == 1, "http_get_once is only defined, and called from http_get and http_get_vps"
    print("PASS: the setup falls back to the server's own address, then GitHub, when git.notrexed.dev fails")


if __name__ == "__main__":
    main()
