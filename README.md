# Hafix-Replication


## Experimental Results Overview

I evaluate multiple prompting strategies for automated bug fixing on the BugsInPy benchmark.
Each bug is tested with 3 samples, and a bug is considered *solved* if at least one sample is correct.

**Key takeaway:**  
Heuristic-aware prompting significantly outperforms history-agnostic baselines in both
sample-level accuracy and bug-level success rate.


## My Limitations

### Model:
 * Due to computational limitations I used **qwen2.5-coder:1.5b**

### Dataset

* Dataset: BugsInPy, a curated Python bug-fixing benchmark.

* Total bugs evaluated: 141 files across multiple projects.

* Each bug was tested with 3 different prompt samples.

### Heuristics

I experimented with different heuristic strategies to guide the model:

* **FLN-ALL**:	Uses Fix Location Heuristics to highlight the exact lines likely to contain bugs.
* **CFN-ALL**:	Combines Contextual Fixing Heuristics with FLN, giving extra weight to context around the bug.
* **FN-ALL**:	Uses Fixing Heuristics Only, without line-level localization.

### Evaluation
Taking in account the time limitations, my approach to evaluation was this:
* Bugs are considered solved if ≥1 sample is correct, which may overestimate practical usability.
  

## Quantitative Results

| Method            | Bugs | Samples | Correct Samples | Accuracy (%) | Bugs Solved (%) |
|-------------------|------|---------|----------------|--------------|----------------|
| Baseline (Instruction) | 36 | 108 | 1 | 0.93 | 2.78 |
| Baseline (InstructionLabel) | 36 | 108 | 2 | 1.85 | 5.56 |
| **FLN-all** | 35 | 105 | 60 | 57.14 | 74.29 |
| **CFN-modified** | 35 | 105 | 57 | 54.29 | 82.86 |
| **FN-all** | 35 | 105 | 49 | 46.67 | 74.29 |



## 📁 Folder Structure


```
prompts/
├─ baseline-prompt.py       # Prompt builder used for baseline data
├─ baseline.py              # Extracts baseline dataset from BugsInPy
├─ heuristics-prompt.py     # Prompt builder for heuristic-based data

heuristics/
├─ extract_heuristics.py    # Script to extract heuristics
├─ cfn-modified/            # CFN-ALL heuristic dataset
├─ fn-all/                  # FN-ALL heuristic dataset
└─ fln-all/                 # FLN-ALL heuristic dataset

data/                        # Contains single-line bugs extracted from BugsInPy

evaluate/
└─ eval.py                   # Evaluation script

outputs/                     # Stores JSON outputs for baseline and heuristic experiments
```





## Things Lacked

* Baselines (Instruction and InstructionLabel) solved almost no bugs, this could be error from my side.
* Limited knowledge and computational resources restricted me to using only these three basic heuristics.
* Evaluation may slightly overestimate practical performance because only ≥1 correct sample is counted as a solved bug.
