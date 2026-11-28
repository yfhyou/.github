#!/usr/bin/env python3
"""Report file references that do not resolve, and numbered sections cited from another file.

Usage: check-references.py ESTATE_DIR REPO [REPO ...]

ESTATE_DIR holds the repos checked out side by side, as /workspaces does in the devcontainer
and the weekly workflow does in CI. Each REPO named is scanned; every repo in ESTATE_DIR
can be the target of a reference, since one repo pointing at another's file is how the
estate keeps one home per thing. Two findings:

  missing   A path like `docs/ADDONS.md` that exists nowhere: not from the repo root, not
            from the referring file's directory, not as the tail of a tracked file's path
            (Ansible docs write `tasks/main.yml` for a role), and not in any sibling repo,
            either named outright (`homelab/docs/gcp.md`) or as the tail of a path there.
            Moved and renamed files are how references usually rot.
  numbered  A section cited by number next to another file's name, e.g. "BUILD-GUIDE.md
            Phase 13". Renumbering that file silently re-points the citation at a different
            section, so cite the section by its name. A file citing its own sections by
            number is allowed: whoever renumbers the file is editing it.

Not paths, and skipped: URLs and bare domains, absolute and home paths (host paths like
/etc/ntfy.conf), globs, brace expansions, variables, and placeholders (an all-caps directory
such as `DIR/`, or `XX` as in `vlanXX`). A line containing `refcheck: ignore` is skipped, for
a reference into someone else's code; `refcheck: ignore-file` in a file's first 15 lines
skips the whole file, for a plan describing paths not yet built or a record of ones since
removed.

Exits 1 when anything is found. It reports; it is run weekly, not as a commit gate.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

TEXT_SUFFIXES = {
    ".md", ".txt", ".sh", ".py", ".yml", ".yaml", ".j2", ".toml", ".cfg", ".conf", ".ini",
    ".service", ".timer", ".json",
}
# Extensions that make a slash-containing token look like a file reference.
REF_SUFFIXES = (
    "md|txt|sh|py|ya?ml|j2|toml|cfg|conf|ini|json|service|timer|network|netdev|link|nft|rules"
)
PATH_RE = re.compile(
    rf"(?<![\w/.~$:-])((?:\.{{1,2}}/)?[\w.-]+(?:/[\w.-]+)+\.(?:{REF_SUFFIXES}))(?![\w/-])"
)
NUMBERED = r"(?:Phase|Step|Addon|Section|Part|Gate)\s+\d+[a-z]?|§\s*\d+(?:\.\d+)*"
FILE_TOKEN = r"[\w./-]*[\w-]\.(?:md|txt)\b`?"
NUMBERED_RE = re.compile(
    rf"({FILE_TOKEN})[^\n]{{0,40}}?({NUMBERED})|({NUMBERED})\s+(?:of|in)\s+`?({FILE_TOKEN})"
)
SKIP_CHARS = set("*?<>{}$[]()|")
# tailscale.com/install.sh: a URL without its scheme, not a path.
DOMAIN_RE = re.compile(r"^[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|dev|me|sh|app)/")
PLACEHOLDER_DIR_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
IGNORE_LINE = "refcheck: ignore"
IGNORE_FILE = "refcheck: ignore-file"


def tracked_files(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, text=True, check=True
    ).stdout
    return [p for p in out.split("\0") if p]


def is_text(path: Path) -> bool:
    if path.suffix in TEXT_SUFFIXES or path.name == "Makefile":
        return True
    if path.suffix:
        return False
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def is_reference(token: str) -> bool:
    if "://" in token or token.startswith(("/", "~", "@", "-", "yfhyou/")):
        return False
    if DOMAIN_RE.match(token) or SKIP_CHARS & set(token) or "..." in token:
        return False
    *dirs, _ = token.split("/")
    if "XX" in token or any(PLACEHOLDER_DIR_RE.match(d) for d in dirs):
        return False
    return True


class Estate:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.files = {
            d.name: tracked_files(d)
            for d in sorted(root.iterdir())
            if (d / ".git").exists()
        }
        self.sets = {name: set(paths) for name, paths in self.files.items()}

    def _in_repo(self, repo: str, token: str) -> bool:
        if token in self.sets[repo] or (self.root / repo / token).exists():
            return True
        suffix = "/" + token
        return any(p.endswith(suffix) for p in self.files[repo])

    def resolves(self, repo: str, referrer: str, token: str) -> bool:
        token = re.split(r"#|:\d", token, maxsplit=1)[0].rstrip(".,;:").removeprefix("./")
        if not token:
            return True
        base = self.root / repo
        if (base / token).exists() or (base / Path(referrer).parent / token).exists():
            return True
        if self._in_repo(repo, token):
            return True
        first, _, rest = token.partition("/")
        if first in self.sets and rest and self._in_repo(first, rest):
            return True
        return any(self._in_repo(other, token) for other in self.sets if other != repo)


def scan(estate: Estate, repo: str) -> list[str]:
    findings = []
    base = estate.root / repo
    for rel in estate.files[repo]:
        path = base / rel
        if path.is_symlink() or not path.is_file() or not is_text(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        if any(IGNORE_FILE in line for line in lines[:15]):
            continue
        for n, line in enumerate(lines, 1):
            if IGNORE_LINE in line:
                continue
            where = f"{repo}/{rel}:{n}"
            for token in sorted({m.group(1) for m in PATH_RE.finditer(line)}):
                if is_reference(token) and not estate.resolves(repo, rel, token):
                    findings.append(f"{where}: missing: `{token}` exists in no repo")
            for m in NUMBERED_RE.finditer(line):
                target = (m.group(1) or m.group(4)).strip("`")
                if Path(target).name == path.name:
                    continue  # a file citing its own sections by number
                section = m.group(2) or m.group(3)
                findings.append(
                    f"{where}: numbered: `{target}` cited by number ({section}); use its name"
                )
    return findings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.splitlines()[2] if __doc__ else "usage error", file=sys.stderr)
        return 2
    estate = Estate(Path(argv[0]))
    unknown = [r for r in argv[1:] if r not in estate.files]
    if unknown:
        print(f"not a repo in {argv[0]}: {', '.join(unknown)}", file=sys.stderr)
        return 2
    findings = [f for repo in argv[1:] for f in scan(estate, repo)]
    print("\n".join(findings))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### {len(findings)} reference finding(s)\n\n")
            fh.writelines(f"- {f}\n" for f in findings)
    print(f"{len(findings)} finding(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
