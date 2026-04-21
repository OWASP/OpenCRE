from typing import List, Optional
import logging

import os
from datetime import datetime
import subprocess
import tempfile

import git
from git.repo.base import Repo
from github import Github

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig()

commit_msg_base = "cre_sync_%s" % (datetime.now().isoformat().replace(":", "."))


def create_branch(branch_name: str) -> None:
    g = git.Git()  # type: ignore
    repo = git.Repo(os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../"))  # type: ignore
    current_branch = repo.active_branch.name
    g.checkout("-b", branch_name)
    g.checkout(current_branch)


def add_to_github(cre_loc: str, alias: str, apikey: str) -> None:
    global commit_msg_base
    commit_msg = "%s-%s" % (commit_msg_base, alias)
    branch_name = commit_msg_base

    repo = git.Repo(os.path.join(os.path.dirname(os.path.realpath(__file__)), "../../"))  # type: ignore
    g = git.Git()  # type: ignore

    logger.info("Adding cre files to branch %s" % branch_name)
    current_branch = repo.active_branch.name
    try:
        g.checkout(branch_name)
        g.add(cre_loc)
        g.commit("-m", commit_msg)

        repo.remotes.origin.push(branch_name)
        remoteURL = [url for url in repo.remotes.origin.urls]
        createPullRequest(
            apiToken=apikey,
            repo=remoteURL[0].replace("git@github.com:", "").replace(".git", ""),
            title=commit_msg,
            srcBranch=commit_msg_base,
            targetBranch="master",
        )

    except git.exc.GitCommandError as gce:  # type: ignore
        # if there's an error (commonly due to no changes, skip pushing a new branch)
        logger.error("Skipping push due to git error trying to sync " + commit_msg)
        logger.error(gce)

    g.checkout(current_branch)


def createPullRequest(
    apiToken: str, repo: str, title: str, srcBranch: str, targetBranch: str = "master"
) -> None:
    logger.info(
        "Issuing pull request from %s to master for repo %s" % (srcBranch, repo)
    )
    github = Github(apiToken)
    body = "CRE Sync %s" % title
    pr = github.get_repo(repo).create_pull(
        title=title, body=body, head=srcBranch, base=targetBranch
    )


def clone(
    source: str,
    dest: Optional[str] = None,
    sparse_paths: Optional[List[str]] = None,
    sparse_cone: bool = True,
    depth: int = 1,
    filter_blob_none: bool = True,
) -> Repo:
    """
    Shallow **clone** (latest commit) with optional **sparse checkout** of subtrees/patterns.

    This is **not** “clone vs cone” as alternatives: you always **clone** the repo; ``cone`` only
    selects how ``git sparse-checkout set`` interprets ``sparse_paths`` (Git’s “cone mode” vs
    gitignore-style patterns). See ``git help sparse-checkout``.

    Steps:

    1. ``git clone --depth N --single-branch [--filter=blob:none] [--sparse] <url> <dest>``
    2. If ``sparse_paths`` is set: ``git -C <dest> sparse-checkout set [--cone|--no-cone] <paths>``

    - ``sparse_cone=True``: use ``--cone``; each entry must be a **single path segment**
      (e.g. ``cheatsheets``), i.e. a top-level directory to include with its contents.
    - ``sparse_cone=False``: use ``--no-cone``; entries are **patterns** (e.g. ``/README.md``,
      ``/**/*.md``, ``site/content/docs/alerts``) for nested paths or file globs.

    Requires Git ≥ 2.25 for ``clone --sparse``; ≥ 2.19 recommended for ``filter=blob:none``.
    """
    if not dest:
        dest = tempfile.mkdtemp()

    clone_cmd = [
        "git",
        "clone",
        "--depth",
        str(depth),
        "--single-branch",
    ]
    if filter_blob_none:
        clone_cmd.extend(["--filter=blob:none"])
    if sparse_paths:
        clone_cmd.append("--sparse")
    clone_cmd.extend([source, dest])

    logger.info(
        "git clone (depth=%s, sparse=%s, filter=blob:none=%s) -> %s",
        depth,
        bool(sparse_paths),
        filter_blob_none,
        dest,
    )
    subprocess.run(clone_cmd, check=True)

    if sparse_paths:
        set_cmd = ["git", "-C", dest, "sparse-checkout", "set"]
        if sparse_cone:
            set_cmd.append("--cone")
        else:
            set_cmd.append("--no-cone")
        set_cmd.extend(sparse_paths)
        logger.info("git sparse-checkout set (%s paths)", len(sparse_paths))
        subprocess.run(set_cmd, check=True)

    return Repo(dest)
