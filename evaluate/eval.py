import json
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
import re

OUTPUTS_DIR = Path("outputs")
DATA_DIR = Path("data")
RESULTS_DIR = Path("results")

RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def normalize_code(code: str) -> str:
    """Normalize code for comparison."""
    code = re.sub(r'^```python\s*', '', code, flags=re.MULTILINE)
    code = re.sub(r'^```\s*', '', code, flags=re.MULTILINE)
    code = code.strip()
    
    if '#' in code:
        code = code.split('#')[0].strip()
    
    code = ' '.join(code.split())
    
    return code

def is_code_correct(generated: str, expected: str) -> bool:
    """Check if generated code matches expected fix."""
    
    gen_normalized = normalize_code(generated)
    exp_normalized = normalize_code(expected)
    
    
    if gen_normalized == exp_normalized:
        return True
    
    
    if exp_normalized in gen_normalized:
        return True
    
    
    
    gen_no_quotes = gen_normalized.replace('"', "'")
    exp_no_quotes = exp_normalized.replace('"', "'")
    
    if gen_no_quotes == exp_no_quotes:
        return True
    
    return False




def evaluate_output_file(output_file: Path, experiment_type: str) -> Dict:
    """Evaluate outputs against expected fix."""
    try:
        
        with open(output_file, "r", encoding="utf-8") as f:
            output_data = json.load(f)
        
        project = output_data.get("project", "unknown")
        bug_id = output_data.get("bug_id", "unknown")
        
        print(f"\n{'='*60}")
        print(f"Evaluating: {project} / bug_{bug_id} / {experiment_type}")
        print(f"{'='*60}")
        
        
        bug_data_file = DATA_DIR / project / f"bug_{bug_id}.json"
        if not bug_data_file.exists():
            print(f"  ⚠️  Bug data not found: {bug_data_file}")
            return None
        
        with open(bug_data_file, "r", encoding="utf-8") as f:
            bug_data = json.load(f)
        
        
        single_change = bug_data.get("single_line_change", {})
        expected_fix = single_change.get("added", "")
        
        if not expected_fix:
            print(f"  ⚠️  No expected fix found")
            return None
        
        print(f"\n  Expected fix:")
        print(f"    {expected_fix}")
        
        
        if experiment_type == "baseline":
            
            results = {}
            
            for style in ["Instruction", "InstructionLabel", "InstructionMask"]:
                outputs = output_data.get("outputs", {}).get(style, [])
                if not outputs:
                    continue
                
                print(f"\n  [{style}] Evaluating {len(outputs)} samples...")
                
                correct_samples = []
                for i, generated in enumerate(outputs):
                    is_correct = is_code_correct(generated, expected_fix)
                    correct_samples.append(is_correct)
                    
                    status = "✓" if is_correct else "✗"
                    print(f"    {status} Sample {i+1}: {generated[:60]}...")
                
                n = len(outputs)
                c = sum(correct_samples)
                
                results[style] = {
                    "total_samples": n,
                    "correct_samples": c,
                    "accuracy": c / n if n > 0 else 0,
                    "individual_results": correct_samples
                }
                
                print(f"    → Accuracy: {c}/{n} = {c/n*100:.1f}%")
            
            return {
                "project": project,
                "bug_id": bug_id,
                "experiment": experiment_type,
                "expected_fix": expected_fix,
                "results": results
            }
        
        else:
            
            outputs = output_data.get("outputs", [])
            if not outputs:
                print(f"  ⚠️  No outputs found")
                return None
            
            print(f"\n  Evaluating {len(outputs)} samples...")
            
            correct_samples = []
            for i, generated in enumerate(outputs):
                is_correct = is_code_correct(generated, expected_fix)
                correct_samples.append(is_correct)
                
                status = "✓" if is_correct else "✗"
                print(f"    {status} Sample {i+1}: {generated[:60]}...")
            
            n = len(outputs)
            c = sum(correct_samples)
            
            print(f"    → Accuracy: {c}/{n} = {c/n*100:.1f}%")
            
            heuristic_info = output_data.get("heuristic", {})
            
            return {
                "project": project,
                "bug_id": bug_id,
                "experiment": experiment_type,
                "heuristic": heuristic_info,
                "expected_fix": expected_fix,
                "results": {
                    "total_samples": n,
                    "correct_samples": c,
                    "accuracy": c / n if n > 0 else 0,
                    "individual_results": correct_samples
                }
            }
    
    except Exception as e:
        print(f"  ❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return None




def aggregate_results(all_results: List[Dict]) -> Dict:
    """Aggregate results across all bugs."""
    
    
    by_experiment = defaultdict(list)
    
    for result in all_results:
        if result:
            exp_type = result["experiment"]
            by_experiment[exp_type].append(result)
    
    aggregated = {}
    
    for exp_type, results in by_experiment.items():
        if exp_type == "baseline":
            
            by_style = defaultdict(list)
            
            for r in results:
                for style, style_results in r.get("results", {}).items():
                    by_style[style].append(style_results)
            
            style_aggregates = {}
            for style, style_results in by_style.items():
                total_samples = sum(r["total_samples"] for r in style_results)
                total_correct = sum(r["correct_samples"] for r in style_results)
                total_bugs = len(style_results)
                
                style_aggregates[style] = {
                    "total_bugs": total_bugs,
                    "total_samples": total_samples,
                    "total_correct": total_correct,
                    "overall_accuracy": total_correct / total_samples if total_samples > 0 else 0,
                    "bugs_with_at_least_one_correct": sum(1 for r in style_results if r["correct_samples"] > 0),
                    "bugs_solved_rate": sum(1 for r in style_results if r["correct_samples"] > 0) / total_bugs if total_bugs > 0 else 0
                }
            
            aggregated[exp_type] = style_aggregates
        
        else:
            
            total_samples = sum(r["results"]["total_samples"] for r in results)
            total_correct = sum(r["results"]["correct_samples"] for r in results)
            total_bugs = len(results)
            
            aggregated[exp_type] = {
                "total_bugs": total_bugs,
                "total_samples": total_samples,
                "total_correct": total_correct,
                "overall_accuracy": total_correct / total_samples if total_samples > 0 else 0,
                "bugs_with_at_least_one_correct": sum(1 for r in results if r["results"]["correct_samples"] > 0),
                "bugs_solved_rate": sum(1 for r in results if r["results"]["correct_samples"] > 0) / total_bugs if total_bugs > 0 else 0
            }
    
    return aggregated




if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("CODE CORRECTNESS EVALUATOR")
    print(f"{'='*60}\n")
    
    
    output_files = []
    
    
    baseline_dir = OUTPUTS_DIR / "baseline"
    if baseline_dir.exists():
        for project_dir in baseline_dir.iterdir():
            if project_dir.is_dir():
                for output_file in project_dir.glob("bug_*.json"):
                    output_files.append((output_file, "baseline"))
    
    
    heuristics_dir = OUTPUTS_DIR / "heuristics"
    if heuristics_dir.exists():
        for heuristic_type in ["cfn-modified", "fln-all", "fn-all"]:
            h_dir = heuristics_dir / heuristic_type
            if h_dir.exists():
                for project_dir in h_dir.iterdir():
                    if project_dir.is_dir():
                        for output_file in project_dir.glob("bug_*.json"):
                            output_files.append((output_file, heuristic_type))
    
    total_files = len(output_files)
    print(f"Found {total_files} output files to evaluate\n")
    
    if total_files == 0:
        print("❌ No output files found!")
        exit(1)
    
    
    all_results = []
    successful = 0
    failed = 0
    
    for idx, (output_file, exp_type) in enumerate(output_files, 1):
        print(f"\n[{idx}/{total_files}] {output_file.relative_to(OUTPUTS_DIR)}")
        
        result = evaluate_output_file(output_file, exp_type)
        if result:
            all_results.append(result)
            successful += 1
            
            
            result_file = RESULTS_DIR / f"{exp_type}_{result['project']}_bug_{result['bug_id']}.json"
            with open(result_file, "w", encoding="utf-8") as f:
                pass
                
        else:
            failed += 1
    
    
    if all_results:
        print(f"\n{'='*60}")
        print("AGGREGATING RESULTS")
        print(f"{'='*60}")
        
        aggregated = aggregate_results(all_results)
        
        
        agg_file = RESULTS_DIR / "aggregated_results.json"
        with open(agg_file, "w", encoding="utf-8") as f:
            json.dump(aggregated, f, indent=2)
        
        
        print(f"\n{'='*60}")
        print("FINAL RESULTS")
        print(f"{'='*60}")
        
        for exp_type, metrics in aggregated.items():
            print(f"\n{exp_type.upper()}:")
            
            if isinstance(metrics, dict) and "total_bugs" in metrics:
                
                print(f"  Total bugs: {metrics['total_bugs']}")
                print(f"  Total samples: {metrics['total_samples']}")
                print(f"  Correct samples: {metrics['total_correct']}")
                print(f"  Overall accuracy: {metrics['overall_accuracy']*100:.2f}%")
                print(f"  Bugs solved (≥1 correct): {metrics['bugs_with_at_least_one_correct']}/{metrics['total_bugs']} ({metrics['bugs_solved_rate']*100:.2f}%)")
            else:
                
                for style, style_metrics in metrics.items():
                    print(f"\n  {style}:")
                    print(f"    Total bugs: {style_metrics['total_bugs']}")
                    print(f"    Total samples: {style_metrics['total_samples']}")
                    print(f"    Correct samples: {style_metrics['total_correct']}")
                    print(f"    Overall accuracy: {style_metrics['overall_accuracy']*100:.2f}%")
                    print(f"    Bugs solved (≥1 correct): {style_metrics['bugs_with_at_least_one_correct']}/{style_metrics['total_bugs']} ({style_metrics['bugs_solved_rate']*100:.2f}%)")
        
        print(f"\n{'='*60}")
        print(f"✅ Results saved to {agg_file}")
        print(f"{'='*60}")
    
    print(f"{'='*60}")
    print(f"Total files evaluated: {total_files}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    