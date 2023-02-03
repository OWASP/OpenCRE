from typing import Optional
import logging

import os
from datetime import datetime
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
        title=title, body=body, head=srcBranch, base="master"
    )


def clone(source: str, dest: Optional[str] = None):
    class Progress(git.remote.RemoteProgress):
        def update(self, op_code, cur_count, max_count=None, message=""):
            print(f"update({op_code}, {cur_count}, {max_count}, {message})")

    if not dest:
        dest = tempfile.mkdtemp()
    with git.Git().custom_environment():
        repo = Repo.clone_from(url=source, to_path=dest, progress=Progress())
        return repo
