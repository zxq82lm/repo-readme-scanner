# repo-readme-scanner

CLI that scans a Git repository (GitHub URL or local path), finds every `README.md`, and outputs **HTML+CSV** with: **index**, **project** (parent dir or `.` for the root), **README link**, and **size (bytes)**.

## Usage
```bash
python3 main.py REPO [-b BRANCH] [-o out.html] [-c out.csv]

# Example
python3 main.py https://github.com/repository -o readmes.html -c readmes.csv
```
