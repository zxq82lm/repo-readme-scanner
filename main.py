#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
import shutil
import subprocess
import html
import csv
from urllib.parse import urlparse, quote

def run(cmd, cwd=None):
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDERR:\n{res.stderr}")
    return res.stdout.strip()

def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://") or s.endswith(".git")

def parse_github(url: str):
    """
    Returns (owner, repo) or (None, None) if not GitHub.
    Accepts https://github.com/owner/repo or .../owner/repo.git
    """
    try:
        u = urlparse(url)
        if "github.com" not in u.netloc.lower():
            return None, None
        parts = [p for p in u.path.split("/") if p]
        if len(parts) < 2:
            return None, None
        owner, repo = parts[0], parts[1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo
    except Exception:
        return None, None

def current_branch(repo_root: str, fallback: str = "main") -> str:
    # Try to determine the current branch (useful for GitHub /blob/<branch>/path links)
    for cmd in [
        ["git", "symbolic-ref", "--short", "HEAD"],
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
    ]:
        try:
            br = run(cmd, cwd=repo_root)
            if br and br != "HEAD":
                return br
        except Exception:
            pass
    return fallback

def find_readmes(root: str):
    """
    Returns a list of dicts: {
        'project': "." if README at root, otherwise parent folder name,
        'rel_path': relative path of README,
        'size_bytes': file size in bytes,
        'abs_path': absolute path,
        'depth': depth (0 = root)
    }
    """
    rows = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.lower() == "readme.md":
                full_path = os.path.join(dirpath, fn)
                rel_path = os.path.relpath(full_path, root).replace("\\", "/")
                parent_dir_path = os.path.dirname(full_path)
                parent_base = os.path.basename(parent_dir_path)

                # Project = "." if README at root, otherwise parent folder
                is_root = rel_path.lower() == "readme.md"
                project_name = "." if is_root else (parent_base if parent_base else ".")

                size_bytes = os.path.getsize(full_path)
                depth = 0 if is_root else rel_path.count("/")

                rows.append({
                    "project": project_name,
                    "rel_path": rel_path,
                    "size_bytes": size_bytes,
                    "abs_path": full_path,
                    "depth": depth,
                })
    # sort: increasing depth, then path
    rows.sort(key=lambda r: (r["depth"], r["rel_path"].lower()))
    return rows

def build_readme_link(item, repo_arg: str, repo_root: str, branch_hint: str) -> str:
    """
    Build the clickable URL to the README.
    - If repo_arg is GitHub, link to https://github.com/<owner>/<repo>/blob/<branch>/<rel_path>
    - Otherwise, link file:// absolute (URL-encoded)
    """
    owner, repo = parse_github(repo_arg) if is_url(repo_arg) else (None, None)
    rel_path = item["rel_path"].replace("\\", "/")
    if owner and repo:
        br = branch_hint or "main"
        return f"https://github.com/{owner}/{repo}/blob/{br}/{quote(rel_path)}"
    abspath = os.path.abspath(item["abs_path"])
    return f"file://{quote(abspath)}"

def generate_html(rows, output_path: str, title: str, repo_arg: str, repo_root: str, branch_hint: str):
    # Minimal HTML + some CSS
    head = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.5rem; }}
  .meta {{ color: #555; margin-bottom: 1rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
  th {{ background: #f6f8fa; text-align: left; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="meta">
  Source: <code>{html.escape(repo_arg)}</code>
</div>
<table>
  <thead>
    <tr>
      <th>Project</th>
      <th>README</th>
      <th class="num">Size (bytes)</th>
    </tr>
  </thead>
  <tbody>
"""
    body_rows = []
    for it in rows:
        link = build_readme_link(it, repo_arg=repo_arg, repo_root=repo_root, branch_hint=branch_hint)
        project = html.escape(it["project"])  # "." for root
        label = html.escape(it["rel_path"])
        size = f"{it['size_bytes']:,}".replace(",", " ")
        body_rows.append(
            f'    <tr><td>{project}</td><td><a href="{link}" target="_blank" rel="noopener noreferrer">{label}</a></td><td class="num">{size}</td></tr>'
        )
    tail = """
  </tbody>
</table>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(body_rows) + tail)

def generate_csv(rows, csv_path: str, repo_arg: str, repo_root: str, branch_hint: str):
    """
    Write a CSV with columns:
    index, project, readme_url, size_bytes  (index 1→N)
    """
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["index", "project", "readme_url", "size_bytes"])
        for idx, it in enumerate(rows, start=1):
            url = build_readme_link(it, repo_arg=repo_arg, repo_root=repo_root, branch_hint=branch_hint)
            w.writerow([idx, it["project"], url, it["size_bytes"]])

def main():
    parser = argparse.ArgumentParser(description="Generate an HTML + CSV inventory of README.md files in a repo.")
    parser.add_argument("repo", help="Git URL (e.g., https://github.com/elodin-sys/elodin) or local path")
    parser.add_argument("-b", "--branch", default=None, help="Branch or tag to checkout (optional)")
    parser.add_argument("-o", "--output", default="readme_inventory.html", help="Output HTML filename")
    parser.add_argument("-c", "--csv-output", default="readme_inventory.csv", help="Output CSV filename")
    args = parser.parse_args()

    workdir = None
    repo_root = None
    try:
        if is_url(args.repo):
            repo_url = args.repo.rstrip("/")
            repo_url_git = repo_url if repo_url.endswith(".git") else repo_url + ".git"

            workdir = tempfile.mkdtemp(prefix="repo_")
            print(f"Cloning into temp dir: {workdir}", file=sys.stderr)
            clone_cmd = ["git", "clone", "--depth", "1", repo_url_git, workdir]
            if args.branch:
                clone_cmd = ["git", "clone", "--depth", "1", "--branch", args.branch, repo_url_git, workdir]
            run(clone_cmd)
            repo_root = workdir
        else:
            repo_root = os.path.abspath(args.repo)
            if not os.path.isdir(repo_root):
                raise RuntimeError(f"Local path does not exist: {repo_root}")

        branch_used = args.branch or current_branch(repo_root, fallback="main")
        rows = find_readmes(repo_root)
        title = "README Inventory"

        generate_html(
            rows=rows,
            output_path=args.output,
            title=title,
            repo_arg=args.repo,
            repo_root=repo_root,
            branch_hint=branch_used
        )
        generate_csv(
            rows=rows,
            csv_path=args.csv_output,
            repo_arg=args.repo,
            repo_root=repo_root,
            branch_hint=branch_used
        )

        print(f"Wrote {len(rows)} entries to {args.output} and {args.csv_output}")
    finally:
        if workdir and os.path.isdir(workdir):
            shutil.rmtree(workdir, ignore_errors=True)

if __name__ == "__main__":
    main()
