import json
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple
import time




DATA_DIR = Path("data")
OUT_DIR = Path("outputs/baseline")
MODEL = "qwen2.5-coder:1.5b"
N_SAMPLES = 3
MAX_WORKERS = 4  
TIMEOUT = 60  
MAX_RETRIES = 3  

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




def instruction_prompt(func_code: str, buggy_line: int) -> str:
    return f"""You are given a Python function with a bug.
The buggy line is line {buggy_line} in the function below.
Fix the bug and return ONLY the fixed function code.

{func_code}""".strip()

def instruction_label_prompt(func_code: str, buggy_line: int) -> str:
    lines = []
    for i, line in enumerate(func_code.splitlines(), start=1):
        if i == buggy_line:
            lines.append(f"{line}  # <BUGGY LINE>")
        else:
            lines.append(line)
    
    return f"""The buggy line is marked with <BUGGY LINE>.
Fix the bug and return ONLY the fixed function code.

{chr(10).join(lines)}""".strip()

def instruction_mask_prompt(func_code: str, buggy_line: int) -> str:
    lines = []
    for i, line in enumerate(func_code.splitlines(), start=1):
        if i == buggy_line:
            indent = line[:len(line) - len(line.lstrip())]
            lines.append(f"{indent}<FILL ME>")
        else:
            lines.append(line)
    
    return f"""The buggy line is masked as <FILL ME>.
Replace it with the correct code.
Return ONLY the fixed function.

{chr(10).join(lines)}""".strip()




def generate_sample(args: Tuple[str, str, int, int]) -> Tuple[int, str]:
    """Generate a single sample (for parallel execution)."""
    prompt, style, sample_idx, total = args
    result = run_ollama(prompt)
    return sample_idx, result

def generate_parallel(prompt: str, style: str, n_samples: int) -> List[str]:
    """Generate multiple samples in parallel."""
    args_list = [(prompt, style, i, n_samples) for i in range(n_samples)]
    results = [None] * n_samples
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(generate_sample, args): args[2] 
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




def process_bug(bug_file: Path) -> bool:
    """Process a single bug file. Returns True if successful."""
    try:
        with open(bug_file, "r", encoding="utf-8") as f:
            bug = json.load(f)
        
        project = bug.get("project", "unknown")
        bug_id = bug.get("bug_id", "unknown")
        
        print(f"\n{'='*60}")
        print(f"Processing: {project} / bug_{bug_id}")
        print(f"{'='*60}")
        
        
        if "files" not in bug or not bug["files"]:
            raise ValueError("Missing 'files' key in bug data")
        
        file_info = bug["files"][0]
        
        
        if file_info.get("changed_functions"):
            func_data = file_info["changed_functions"][0]
            func_code = func_data.get("function_before", "")
            if not func_code:
                raise ValueError("Empty function_before")
        else:
            raise ValueError("No changed_functions found")
        
        
        if not file_info.get("buggy_line_locations"):
            raise ValueError("No buggy_line_locations found")
        buggy_line = file_info["buggy_line_locations"][0]
        
        
        prompts = {
            "Instruction": instruction_prompt(func_code, buggy_line),
            "InstructionLabel": instruction_label_prompt(func_code, buggy_line),
            "InstructionMask": instruction_mask_prompt(func_code, buggy_line),
        }
        
        
        outputs = {}
        for style, prompt in prompts.items():
            print(f"\n  [{style}] Generating {N_SAMPLES} samples...")
            outputs[style] = generate_parallel(prompt, style, N_SAMPLES)
        
        
        out_dir = OUT_DIR / project
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"bug_{bug_id}.json"
        
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({
                "project": project,
                "bug_id": bug_id,
                "baseline_only": True,
                "outputs": outputs
            }, f, indent=2)
        
        print(f"\n  ✅ Saved → {out_file}")
        return True
    
    except Exception as e:
        print(f"\n  ❌ Failed to process {bug_file}: {e}")
        
        
        try:
            error_file = OUT_DIR / "errors.log"
            with open(error_file, "a", encoding="utf-8") as f:
                f.write(f"{bug_file}: {str(e)}\n")
        except:
            pass
        
        return False




if __name__ == "__main__":
    start_time = time.time()
    
    
    bug_files = []
    for project_dir in DATA_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        bug_files.extend(project_dir.glob("bug_*.json"))
    
    total_bugs = len(bug_files)
    print(f"Found {total_bugs} bug files to process\n")
    
    
    successful = 0
    failed = 0
    
    for idx, bug_file in enumerate(bug_files, 1):
        print(f"\n[{idx}/{total_bugs}] Processing {bug_file.name}")
        if process_bug(bug_file):
            successful += 1
        else:
            failed += 1
    
    
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Total bugs: {total_bugs}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Time elapsed: {elapsed:.2f}s")
    print(f"Average per bug: {elapsed/total_bugs:.2f}s")
    print(f"{'='*60}")