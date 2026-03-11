"""GitHub: fetch issues, clone repos, commit+push, open PRs."""
from __future__ import annotations
import os, re, pathlib, tempfile
import git
from github import Github, GithubException


def _gh() -> Github:
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok:
        raise RuntimeError("GITHUB_TOKEN not set")
    return Github(tok)


def parse_issue_url(url: str) -> tuple:
    pattern = r"github[.]com/([^/]+)/([^/]+)/issues/(\d+)"
    m = re.search(pattern, url)
    if not m:
        raise ValueError(f"Cannot parse: {url}")
    return m.group(1), m.group(2), int(m.group(3))


def fetch_issue(owner: str, repo_name: str, num: int) -> dict:
    repo = _gh().get_repo(f"{owner}/{repo_name}")
    issue = repo.get_issue(num)
    comments = ""
    for c in issue.get_comments():
        comments += f"\n\n--- {c.user.login} ---\n{c.body}"
    return {
        "title": issue.title,
        "body": issue.body or "",
        "full_text": f"Title: {issue.title}\n\n{issue.body or ''}\n{comments}",
        "labels": [l.name for l in issue.labels],
    }


def fork_repo(owner: str, repo_name: str) -> str:
    """Fork the repository to the authenticated user's account."""
    gh = _gh()
    user = gh.get_user()
    
    # Check if fork already exists
    try:
        fork = gh.get_repo(f"{user.login}/{repo_name}")
        print(f"  Fork already exists: {fork.html_url}")
        return f"{user.login}/{repo_name}"
    except GithubException:
        # Fork doesn't exist, create it
        original_repo = gh.get_repo(f"{owner}/{repo_name}")
        fork = original_repo.create_fork()
        print(f"  Created fork: {fork.html_url}")
        return f"{user.login}/{repo_name}"


def clone_repo(owner: str, repo_name: str, target: str | None = None, use_fork: bool = True) -> str:
    """Clone a repository. If use_fork is True, clone from user's fork."""
    tok = os.environ.get("GITHUB_TOKEN", "")
    
    if use_fork:
        # Try to clone from fork first
        try:
            user = _gh().get_user()
            fork_owner = user.login
            url = f"https://{tok}@github.com/{fork_owner}/{repo_name}.git"
            if target is None:
                target = tempfile.mkdtemp(prefix=f"devagent_{repo_name}_")
            git.Repo.clone_from(url, target, depth=1)
            return target
        except Exception:
            # If fork doesn't exist or clone fails, clone original
            print("  Fork not found, cloning original...")
    
    # Clone from original
    url = f"https://{tok}@github.com/{owner}/{repo_name}.git"
    if target is None:
        target = tempfile.mkdtemp(prefix=f"devagent_{repo_name}_")
    git.Repo.clone_from(url, target, depth=1)
    return target


def create_branch(repo_path: str, branch: str) -> None:
    """Create and checkout a new branch."""
    repo = git.Repo(repo_path)
    # Make sure we're on the default branch first
    if repo.active_branch.name != branch:
        repo.git.checkout("-b", branch)


def commit_and_push(repo_path: str, branch: str, message: str, remote_name: str = "origin") -> None:
    """Commit all changes and push to remote."""
    repo = git.Repo(repo_path)
    
    # Configure git user if not set
    with repo.config_writer() as cw:
        if not repo.config_reader().has_option("user", "name"):
            cw.set_value("user", "name", "DevAgent")
        if not repo.config_reader().has_option("user", "email"):
            cw.set_value("user", "email", "devagent@example.com")
    
    # Add all changes
    repo.git.add("-A")
    
    # Check if there are changes to commit
    if repo.is_dirty() or repo.untracked_files:
        try:
            repo.index.commit(message)
        except Exception as e:
            print(f"Warning: Commit failed: {e}")
            return
    
    # Push to remote
    try:
        origin = repo.remote(remote_name)
        
        # CRITICAL FIX: Ensure we're pushing to the fork, not the original
        current_url = origin.url
        user = _gh().get_user()
        
        # If the URL points to the original repo, update it to point to your fork
        if "pallets" in current_url and user.login in current_url:
            # Already pointing to fork, good
            pass
        elif "pallets" in current_url:
            # Still pointing to original, update to fork
            new_url = current_url.replace("pallets", user.login)
            origin.set_url(new_url)
            print(f"  Updated remote from {current_url} to {new_url}")
       
        # Update URL to include token if needed
        if "@" not in origin.url:
            tok = os.environ.get("GITHUB_TOKEN", "")
            if tok:
                new_url = origin.url.replace("https://github.com", f"https://{tok}@github.com")
                origin.set_url(new_url)
        
        origin.push(refspec=f"{branch}:{branch}")
    except Exception as e:
        raise RuntimeError(f"Failed to push to remote: {e}")
    
def commit_changes(repo_path: str, branch_name: str, message: str) -> None:
    """Commit and push changes to the remote repository."""
    try:
        # Create and checkout new branch
        create_branch(repo_path, branch_name)
        # Commit and push changes
        commit_and_push(repo_path, branch_name, message)
    except Exception as e:
        raise RuntimeError(f"Failed to commit changes: {e}")


def open_pull_request(owner: str, repo_name: str, branch: str,
                      issue_num: int, title: str, body: str, 
                      head_repo: str | None = None) -> tuple:
    """Open a pull request on GitHub.
    
    Args:
        owner: Original repository owner
        repo_name: Repository name
        branch: Branch name to create PR from
        issue_num: GitHub issue number (for reference)
        title: PR title
        body: PR description body
        head_repo: The repository where the branch is (for forks). If None, uses owner/repo
    
    Returns:
        Tuple of (pr_url, pr_number)
    """
    try:
        repo = _gh().get_repo(f"{owner}/{repo_name}")
        
        # If head_repo is provided, it's a fork
        if head_repo:
            head = f"{head_repo.split('/')[0]}:{branch}"
        else:
            head = branch
            
        pr = repo.create_pull(
            title=title,
            body=body,
            head=head,
            base=repo.default_branch
        )
        return pr.html_url, pr.number
    except Exception as e:
        raise RuntimeError(f"Failed to create pull request: {e}")


def create_pull_request(owner: str, repo_name: str, repo_path: str, 
                        branch_name: str, issue_number: int, 
                        issue_title: str, pr_body: str) -> str:
    """Create a pull request for the given branch.
    
    Args:
        owner: Original repository owner
        repo_name: Repository name
        repo_path: Local path to the cloned repository
        branch_name: Branch name to create PR from
        issue_number: GitHub issue number
        issue_title: Issue title for PR title
        pr_body: PR description body
    
    Returns:
        PR URL
    """
    # Get the remote URL to determine if we're using a fork
    repo = git.Repo(repo_path)
    remote_url = repo.remote().url
    
    # Determine if this is a fork
    user = _gh().get_user()
    if user.login in remote_url:
        # We're pushing from a fork
        head_repo = f"{user.login}/{repo_name}"
    else:
        head_repo = None
    
    # Generate PR title
    pr_title = f"Fix #{issue_number}: {issue_title}"
    
    # Add reference to issue in body if not already there
    if f"#{issue_number}" not in pr_body:
        pr_body = f"Fixes #{issue_number}\n\n{pr_body}"
    
    # Open the pull request
    pr_url, pr_number = open_pull_request(
        owner=owner,
        repo_name=repo_name,
        branch=branch_name,
        issue_num=issue_number,
        title=pr_title,
        body=pr_body,
        head_repo=head_repo
    )
    
    return pr_url


def detect_test_command(repo_path: str) -> str:
    root = pathlib.Path(repo_path)
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
        return "pytest -x -q --tb=short 2>&1 | head -150"
    if (root / "package.json").exists():
        return "npm test 2>&1 | head -150"
    if (root / "go.mod").exists():
        return "go test ./... 2>&1 | head -150"
    if (root / "Cargo.toml").exists():
        return "cargo test 2>&1 | head -150"
    if (root / "tests").exists() or (root / "test").exists():
        return "pytest -x -q --tb=short 2>&1 | head -150"
    return "pytest -x -q --tb=short 2>&1 | head -150"