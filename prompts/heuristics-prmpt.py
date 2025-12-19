import json
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional
import time




HEURISTICS_DIR = Path("heuristics")
OUT_DIR = Path("outputs/heuristics")
MODEL = "qwen2.5-coder:1.5b"
N_SAMPLES = 3
MAX_WORKERS = 4
TIMEOUT = 60
MAX_RETRIES = 3


HEURISTIC_TYPES = ["cfn-modified", "fln-all", "fn-all"]

OUT_DIR.mkdir(parents=True, exist_ok=True)




def run_ollama(prompt: str, retry_count: int = 0) -> str:
    """Run local Ollama model with timeout and retry logic."""
    try:
        proc = subprocess.run(
            ["ollama", "run", MODEL],
            input=prompt,
            text=True,
            capture_output=True,
            timeout=TIMEOUT
        )
        
        if proc.returncode != 0:
            raise RuntimeError(f"Ollama error: {proc.stderr}")
        
        return proc.stdout.strip()
    
    except subprocess.TimeoutExpired:
        if retry_count < MAX_RETRIES:
            print(f"  ⚠️  Timeout, retrying ({retry_count + 1}/{MAX_RETRIES})...")
            time.sleep(1)
            return run_ollama(prompt, retry_count + 1)
        return "[ERROR: Timeout after retries]"
    
    except Exception as e:
        if retry_count < MAX_RETRIES:
            print(f"  ⚠️  Error: {e}, retrying ({retry_count + 1}/{MAX_RETRIES})...")
            time.sleep(1)
            return run_ollama(prompt, retry_count + 1)
        return f"[ERROR: {str(e)}]"




def build_heuristic_prompt(bug_data: Dict, heuristic_name: str, heuristic_value: List[str]) -> str:
    """Build prompt based on heuristic type."""
    
    
    single_change = bug_data["original_bug"].get("single_line_change", {})
    deleted_line = single_change.get("deleted", "")
    added_line = single_change.get("added", "")
    
    files = bug_data["original_bug"].get("files", [])
    buggy_line = files[0].get("buggy_line_locations", [0])[0] if files else 0
    
    
    if heuristic_name == "CFN-modified":
        
        context = f"""You are analyzing a bug in the following function(s): {', '.join(heuristic_value)}

Bug Location: Line {buggy_line}
Deleted Line: {deleted_line}
Added Line: {added_line}

The bug is in one of these functions. Analyze the change and fix the bug."""
    
    elif heuristic_name == "FLN-all":
        
        context = f"""You are analyzing a bug in the following file(s):
{chr(10).join('- ' + f for f in heuristic_value)}

Bug Location: Line {buggy_line}
Deleted Line: {deleted_line}
Added Line: {added_line}

The bug is in one of these files. Analyze the change and provide the fix."""
    
    elif heuristic_name == "FN-all":
        
        context = f"""You are analyzing a bug that may involve these related functions:
{chr(10).join('- ' + f for f in heuristic_value[:10])}  
... and {len(heuristic_value) - 10} more functions

Bug Location: Line {buggy_line}
Deleted Line: {deleted_line}
Added Line: {added_line}

Analyze the bug and provide the correct fix."""
    
    else:
        context = f"""Bug Location: Line {buggy_line}
Deleted Line: {deleted_line}
Added Line: {added_line}"""
    
    prompt = f"""{context}

Task: Fix the bug by providing the corrected line of code.
Return ONLY the fixed line, without explanations."""
    
    return prompt.strip()




def generate_sample(args: Tuple[str, int, int]) -> Tuple[int, str]:
    """Generate a single sample (for parallel execution)."""
    prompt, sample_idx, total = args
    result = run_ollama(prompt)
    return sample_idx, result

def generate_parallel(prompt: str, n_samples: int) -> List[str]:
    """Generate multiple samples in parallel."""
    args_list = [(prompt, i, n_samples) for i in range(n_samples)]
    results = [None] * n_samples
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(generate_sample, args): args[1] 
                   for args in args_list}
        
        for future in as_completed(futures):
            idx = futures[future]
            try:
                sample_idx, output = future.result()
                results[sample_idx] = output
                print(f"    ✓ Sample {sample_idx + 1}/{n_samples} completed")
            except Exception as e:
                print(f"    ✗ Sample {idx + 1} failed: {e}")
                results[idx] = f"[ERROR: {str(e)}]"
    
    return results




def process_heuristic_file(heuristic_file: Path, heuristic_type: str) -> bool:
    """Process a single heuristic JSON file."""
    try:
        
        with open(heuristic_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        project = data["original_bug"].get("project", "unknown")
        bug_id = data["original_bug"].get("bug_id", "unknown")
        heuristic_name = data["heuristic"]["name"]
        heuristic_value = data["heuristic"]["value"]
        
        print(f"\n{'='*60}")
        print(f"Processing: {project} / bug_{bug_id} / {heuristic_name}")
        print(f"Heuristic values: {len(heuristic_value)} items")
        print(f"{'='*60}")
        
        
        prompt = build_heuristic_prompt(data, heuristic_name, heuristic_value)
        
        
        print(f"\n  Generating {N_SAMPLES} samples...")
        outputs = generate_parallel(prompt, N_SAMPLES)
        
        
        output_data = {
            "project": project,
            "bug_id": bug_id,
            "heuristic": {
                "name": heuristic_name,
                "type": heuristic_type,
                "value": heuristic_value
            },
            "original_bug": data["original_bug"],
            "outputs": outputs
        }
        
        
        out_dir = OUT_DIR / heuristic_type / project
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"bug_{bug_id}.json"
        
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\n  ✅ Saved → {out_file}")
        return True
    
    except Exception as e:
        print(f"\n  ❌ Failed to process {heuristic_file}: {e}")
        
        
        try:
            error_file = OUT_DIR / "errors.log"
            with open(error_file, "a", encoding="utf-8") as f:
                f.write(f"{heuristic_file}: {str(e)}\n")
        except:
            pass
        
        return False




if __name__ == "__main__":
    start_time = time.time()
    
    
    all_files = []
    stats = {h_type: 0 for h_type in HEURISTIC_TYPES}
    
    for heuristic_type in HEURISTIC_TYPES:
        heuristic_dir = HEURISTICS_DIR / heuristic_type
        
        if not heuristic_dir.exists():
            print(f"⚠️  Directory not found: {heuristic_dir}")
            continue
        
        
        for project_dir in heuristic_dir.iterdir():
            if not project_dir.is_dir():
                continue
            
            for bug_file in project_dir.glob("bug_*.json"):
                all_files.append((bug_file, heuristic_type))
                stats[heuristic_type] += 1
    
    total_files = len(all_files)
    print(f"\n{'='*60}")
    print(f"HEURISTICS PROCESSING")
    print(f"{'='*60}")
    print(f"Total files to process: {total_files}")
    for h_type, count in stats.items():
        print(f"  - {h_type}: {count} files")
    print(f"{'='*60}\n")
    
    if total_files == 0:
        print("❌ No files found to process!")
        exit(1)
    
    
    successful = 0
    failed = 0
    
    for idx, (bug_file, heuristic_type) in enumerate(all_files, 1):
        print(f"\n[{idx}/{total_files}] Processing {bug_file.name} ({heuristic_type})")
        if process_heuristic_file(bug_file, heuristic_type):
            successful += 1
        else:
            failed += 1
    
    
    elapsed = time.time() - start_time
    print(f"SUMMARY")
    print(f"Total files: {total_files}")
    print(f"Successful: {successful} ({successful/total_files*100:.1f}%)")
    print(f"Failed: {failed} ({failed/total_files*100:.1f}%)")
    print(f"Time elapsed: {elapsed:.2f}s ({elapsed/60:.2f} minutes)")
    print(f"Average per file: {elapsed/total_files:.2f}s")
    