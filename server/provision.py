"""Work-repo provisioning — one private git repo per user, fully managed by us.

The loan officer never sees git. They pick a region at first login; this layer
turns that into a private repo on the right host and hands the app back a
ready-to-clone URL (credentials embedded where the host requires it).

Provisioners
------------
* ``local``   — bare repo on this server's disk (``file://`` style path URL).
                Dev/pilot default: zero external accounts, the whole loop runs
                on one box.
* ``github``  — private repo under ``GITHUB_ORG`` (or the token's own user)
                via the GitHub REST API; seeded over the contents API, so no
                git binary is needed server-side. Needs ``GITHUB_TOKEN``
                (classic PAT with ``repo`` scope, or a fine-grained token with
                repo create + contents write).
* ``codeup``  — China-build host. Private repo under our Codeup organization
                via the oapi/v1 REST API (personal access token in the
                ``x-yunxiao-token`` header — no Aliyun AK/SK signing needed).
                Needs ``CODEUP_TOKEN`` (PAT with repo + file read/write) and
                ``CODEUP_ORG_ID`` (the org id in the codeup.aliyun.com URL).

Selection: region → host mapping lives in ``REGION_MAP``; the ``PROVISIONER``
env var overrides both regions with a single host (``PROVISIONER=local`` is
the dev default).

Every provisioner returns ``(work_repo_url, git_token)``. The URL must be
directly cloneable by the app; ``git_token`` is kept separate for the future
short-lived-token rotation and is empty where the URL already carries auth.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


class ProvisioningError(RuntimeError):
    """Repo couldn't be created; the message is shown to the user verbatim."""


# Region choice (user-facing) → git host (implementation detail the user
# never sees). Kept here so the mapping changes in one place.
REGION_MAP = {
    "cn": "codeup",
    "intl": "github",
}

# The skeleton every fresh work repo must contain — workrepo.py's structural
# check refuses a checkout without clients/ and products/.
SEED_FILES = {
    "README.md": (
        "# Mortgage Work — work repo\n\n"
        "This repo is your book of business: one folder per client under "
        "`clients/`, lender product paperwork under `products/`. The app "
        "keeps it in sync — edit here or in the app, never both at once.\n"
    ),
    # Seeded here (not just self-healed on first boot) so a repo whose first
    # app session dies before the boot flush still ships with the ignore
    # list. Content mirrors workrepo.py's GITIGNORE_HEADER + GITIGNORE_ENTRIES
    # byte-for-byte — the boot self-heal must find nothing to add.
    ".gitignore": (
        "# Machine-managed by the workspace app — device noise only.\n"
        "# Work files (documents, index.jsonl, AGENTS.md) are never ignored.\n"
        "\n"
        ".DS_Store\n"
        "Thumbs.db\n"
        "Desktop.ini\n"
        "/session.json\n"
        "/.seeka/\n"
        "/.tmp/\n"
        "~$*\n"
        "*.part\n"
        "*.crdownload\n"
    ),
    "clients/.gitkeep": "",
    "products/.gitkeep": "",
}


def provisioner_for(region: str):
    """Resolve the host for a region (env override wins) and build it."""
    name = os.environ.get("PROVISIONER", "").lower() or REGION_MAP.get(region)
    if name == "local":
        return LocalProvisioner(_data_dir() / "repos")
    if name == "github":
        return GithubProvisioner()
    if name == "codeup":
        return CodeupProvisioner()
    raise ProvisioningError(f"unknown provisioning host: {name!r}")


def _data_dir() -> Path:
    """Server data root (SQLite lives here too) — env override for tests."""
    root = Path(os.environ.get(
        "AUTH_DATA_DIR", Path(__file__).resolve().parent / "data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


# ── Local: bare repos on this machine ──


class LocalProvisioner:
    """Dev/pilot host: a bare repo per user under the server data dir.

    The clone URL is a plain filesystem path — git accepts it as-is, no auth
    involved. Only useful while everything runs on one box.
    """

    def __init__(self, repos_dir: Path):
        self.repos_dir = repos_dir

    def provision(self, uid: str, email: str, name: str) -> tuple[str, str]:
        repo = self.repos_dir / f"{uid}.git"
        if repo.is_dir():
            return str(repo), ""
        self.repos_dir.mkdir(parents=True, exist_ok=True)

        def git(args: list[str], cwd: Path | None = None):
            res = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                raise ProvisioningError(f"git {' '.join(args)} failed: {res.stderr.strip()[:200]}")

        git(["init", "--bare", "-b", "main", str(repo)])
        # Seed the skeleton from a throwaway working copy, then push it into
        # the bare repo — bare repos can't be written to directly.
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "seed"
            work.mkdir()
            git(["init", "-b", "main"], cwd=work)
            for rel, content in SEED_FILES.items():
                dest = work / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
            git(["add", "-A"], cwd=work)
            git(["-c", f"user.email={email}", "-c", f"user.name={name}",
                 "commit", "-m", "Initial work repo"], cwd=work)
            git(["remote", "add", "origin", str(repo)], cwd=work)
            git(["push", "origin", "main"], cwd=work)
        log.info("provisioned local work repo %s", repo)
        return str(repo), ""


# ── GitHub: private repo under our org/user ──


class GithubProvisioner:
    """Creates the private repo under OUR account (org or the token's user) —
    the LO never owns or even sees it. The long-lived token comes back
    embedded in the clone URL; replacing it with short-lived GitHub App
    installation tokens is the post-pilot step.
    """

    API = "https://api.github.com"

    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        if not self.token:
            raise ProvisioningError(
                "GitHub provisioning needs GITHUB_TOKEN (a PAT with repo scope)")
        # Explicit org wins; otherwise the repo lands under the token's user.
        self.org = os.environ.get("GITHUB_ORG", "").strip()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.API,
            headers={"Authorization": f"Bearer {self.token}",
                     "Accept": "application/vnd.github+json"},
            timeout=30,
        )

    def provision(self, uid: str, email: str, name: str) -> tuple[str, str]:
        repo_name = f"mw-{uid}"
        with self._client() as c:
            owner = self.org or c.get("/user").json().get("login")
            if not owner:
                raise ProvisioningError("couldn't resolve the GitHub owner for the new repo")
            # Create-if-missing: a repeat first login (provisioning crashed
            # after the repo landed) must heal, not 422.
            res = c.post(
                f"/orgs/{owner}/repos" if self.org else "/user/repos",
                json={"name": repo_name, "private": True, "auto_init": False})
            if res.status_code == 422 and "name already exists" in res.text:
                pass  # repo from a previous attempt — adopt it
            elif res.status_code >= 300:
                raise ProvisioningError(
                    f"GitHub refused to create the repo ({res.status_code}): {res.text[:200]}")
            # Seed the skeleton; 422 on a file means it's already there.
            for rel, content in SEED_FILES.items():
                put = c.put(
                    f"/repos/{owner}/{repo_name}/contents/{rel}",
                    json={"message": f"Seed {rel}",
                          "branch": "main",
                          "content": base64.b64encode(content.encode()).decode()})
                if put.status_code >= 300 and put.status_code != 422:
                    raise ProvisioningError(
                        f"GitHub seed of {rel} failed ({put.status_code}): {put.text[:200]}")
        # x-access-token works for both PATs and App tokens as the username.
        url = f"https://x-access-token:{self.token}@github.com/{owner}/{repo_name}.git"
        log.info("provisioned github work repo %s/%s", owner, repo_name)
        return url, self.token


# ── Codeup: private repo under our Codeup organization ──


class CodeupProvisioner:
    """China-build host. Same shape as the GitHub flow: the repo lands under
    OUR organization (the LO never owns it), seeded over the files API so the
    server needs no git binary, and the clone URL carries the long-lived PAT
    (``https://oauth2:<token>@…`` — the format Codeup accepts, already proven
    by the skills market clone).

    Uses the oapi/v1 REST API with a personal access token — no Aliyun
    AK/SK signing. Post-pilot step mirrors GitHub's: swap the shared PAT for
    per-user short-lived credentials.
    """

    def __init__(self):
        self.token = os.environ.get("CODEUP_TOKEN", "")
        self.org_id = os.environ.get("CODEUP_ORG_ID", "").strip()
        # API endpoint ≠ git/web domain: the central-edition OpenAPI lives on
        # openapi-rdc.aliyuncs.com; hitting codeup.aliyun.com with an API call
        # just 302s to the Aliyun login page.
        self.domain = os.environ.get("CODEUP_DOMAIN", "openapi-rdc.aliyuncs.com").strip()
        missing = [n for n, v in (("CODEUP_TOKEN", self.token),
                                  ("CODEUP_ORG_ID", self.org_id)) if not v]
        if missing:
            raise ProvisioningError(
                f"Codeup provisioning needs {', '.join(missing)} in server/.env")

    def _client(self) -> httpx.Client:
        # Central-edition (中心版) endpoints: org id travels in the path and
        # the PAT in the x-yunxiao-token header.
        return httpx.Client(
            base_url=f"https://{self.domain}/oapi/v1/codeup/organizations/{self.org_id}",
            headers={"x-yunxiao-token": self.token},
            timeout=30,
        )

    def provision(self, uid: str, email: str, name: str) -> tuple[str, str]:
        repo_path = f"mw-{uid}"
        with self._client() as c:
            # Create-if-missing: a repeat first login (provisioning crashed
            # after the repo landed) must heal, not fail on "path exists".
            res = c.post("/repositories", json={
                "name": repo_path, "path": repo_path,
                "visibility": "private",
                # EMPTY would still leave the repo branchless; we seed the
                # skeleton ourselves below.
            })
            if res.status_code < 300:
                repo = res.json()
            else:
                repo = self._adopt(c, repo_path, res)
            repo_id = repo.get("id")
            full_path = repo.get("pathWithNamespace") or f"{self.org_id}/{repo_path}"
            if not repo_id:
                raise ProvisioningError("Codeup created the repo but returned no id")
            # Seed the skeleton. Primary path is the files API (no git binary
            # needed server-side), but it needs the PAT's 文件 read/write
            # scope — a token created only for git + repo management gets a
            # 403 there, so fall back to clone+commit+push, which the same
            # token always covers (its raison d'être). A fresh Codeup repo
            # has no branch yet; the first push creates it.
            try:
                self._seed_via_files_api(c, repo_id)
            except ProvisioningError as e:
                log.info("files API seeding unavailable (%s); using git push", e)
                self._seed_via_git(repo.get("httpUrlToRepo") or
                                   f"https://codeup.aliyun.com/{full_path}.git",
                                   email, name)
        # oauth2:<PAT> is the HTTPS credential pair Codeup accepts. Prefer the
        # clone URL the API returns (httpUrlToRepo) over hand-building it.
        clean_url = repo.get("httpUrlToRepo") or \
            f"https://codeup.aliyun.com/{full_path}.git"
        url = clean_url.replace("https://", f"https://oauth2:{self.token}@", 1)
        log.info("provisioned codeup work repo %s", full_path)
        return url, self.token

    def _seed_via_files_api(self, c: httpx.Client, repo_id):
        """One commit per file through the files API. Raises ProvisioningError
        on any non-'already exists' failure so the caller can fall back."""
        for rel, content in SEED_FILES.items():
            put = c.post(
                f"/repositories/{repo_id}/files",
                json={"branch": "master",
                      "commitMessage": f"Seed {rel}",
                      "filePath": rel,
                      "content": content,
                      "encoding": "text"})
            if put.status_code >= 300 and not _file_already_there(put):
                raise ProvisioningError(
                    f"Codeup seed of {rel} failed ({put.status_code}): {put.text[:200]}")

    def _seed_via_git(self, clone_url: str, email: str, name: str):
        """Fallback seeder: clone (a just-created repo is empty — git tolerates
        that), write the skeleton over whatever's there, push. Needs a git
        binary server-side, but works with any PAT that can push — i.e. the
        same credential that made the repo usable at all."""
        auth_url = clone_url.replace("https://", "https://oauth2:" + self.token + "@", 1)

        def git(args: list[str], cwd: Path | None = None):
            res = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                raise ProvisioningError(f"git {' '.join(args)} failed: {res.stderr.strip()[:200]}")

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "seed"
            # Clone inherits the remote's default branch, so the push below
            # lands on master/main whatever the host picked.
            git(["clone", "-q", auth_url, str(work)])
            for rel, content in SEED_FILES.items():
                dest = work / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
            git(["add", "-A"], cwd=work)
            # A retried provisioning where every file already exists has
            # nothing to commit — that's success, not failure.
            staged = subprocess.run(
                ["git", "diff", "--cached", "--quiet"], cwd=work,
                capture_output=True, text=True)
            if staged.returncode != 0:
                git(["-c", f"user.email={email}", "-c", f"user.name={name}",
                     "commit", "-m", "Initial work repo"], cwd=work)
                git(["push", "origin", "HEAD"], cwd=work)

    def _adopt(self, c: httpx.Client, repo_path: str, create_res) -> dict:
        """Create failed — if the repo already exists, adopt it; otherwise
        surface the real error instead of guessing."""
        # GetRepository accepts the URL-encoded full path in place of the id.
        encoded = f"{self.org_id}%2F{repo_path}"
        got = c.get(f"/repositories/{encoded}")
        if got.status_code < 300 and got.json().get("id"):
            return got.json()
        raise ProvisioningError(
            f"Codeup refused to create the repo ({create_res.status_code}): "
            f"{create_res.text[:200]}")


def _file_already_there(res) -> bool:
    """Heuristic for 'the seed file exists' on a retried provisioning — the
    files API has no dedicated status code, so we sniff the body."""
    if res.status_code == 409:
        return True
    body = res.text.lower()
    return res.status_code == 400 and ("exist" in body or "已存在" in res.text)
