import json
import ast
import base64
import requests
from pathlib import Path
import time
import os 


GITHUB_TOKEN = ("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

DATA_DIR = Path("data")           
OUT_DIR = Path("heuristics")      

def github_get(url):
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_commit_files(owner, repo, sha):
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
    data = github_get(url)
    return [f["filename"] for f in data["files"]]

def get_file_at_commit(owner, repo, path, sha):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={sha}"
    data = github_get(url)
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content

def extract_functions(source):
    tree = ast.parse(source)
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            funcs.append({
                "name": node.name,
                "start": node.lineno,
                "end": node.end_lineno
            })
    return funcs




def process_bug(bug_path):
    with open(bug_path, "r", encoding="utf-8") as f:
        bug = json.load(f)

    project = bug["project"]
    bug_id = bug["bug_id"]
    fix_sha = bug["bug_description"]["fixed_commit_id"]

    
    owner, repo = project, project

    file_info = bug["files"][0]
    file_path = file_info["buggy_file_path"].split(" b/")[-1]
    buggy_lines = file_info["buggy_line_locations"]

    try:
        
        
        
        fln_all = get_commit_files(owner, repo, fix_sha)

        
        
        
        source = get_file_at_commit(owner, repo, file_path, fix_sha)
        functions = extract_functions(source)
        fn_all = [f["name"] for f in functions]

        
        
        
        cfn_modified = [
            f["name"] for f in functions
            if any(f["start"] <= line <= f["end"] for line in buggy_lines)
        ]

        heuristics = {
            "FLN-all": fln_all,
            "FN-all": fn_all,
            "CFN-modified": cfn_modified
        }

        
        for h_name, value in heuristics.items():
            out_path = OUT_DIR / h_name.lower() / project
            out_path.mkdir(parents=True, exist_ok=True)

            out_file = out_path / f"bug_{bug_id}.json"
            out_data = {
                "original_bug": bug,
                "heuristic": {
                    "name": h_name,
                    "value": value
                }
            }

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2)

            print(f"[✓] {h_name} → {project}/bug_{bug_id}.json")

        
        time.sleep(0.5)

    except Exception as e:
        print(f"[✗] Error processing {project}/bug_{bug_id}: {e}")




if __name__ == "__main__":
    for project_dir in DATA_DIR.iterdir():
        if project_dir.is_dir():
            for bug_file in project_dir.glob("*.json"):
                process_bug(bug_file)
