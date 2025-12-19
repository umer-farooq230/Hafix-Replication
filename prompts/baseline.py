import os
import json
import re
from pathlib import Path


class BugsInPyAnalyzer:
    def __init__(self, bugsinpy_path):
        self.bugsinpy_path = bugsinpy_path
        self.projects_path = os.path.join(bugsinpy_path, "projects")
        self.output_base = "data"
        
    def get_all_projects(self):
        """Get list of all projects"""
        if not os.path.exists(self.projects_path):
            return []
        return sorted([d for d in os.listdir(self.projects_path) 
                      if os.path.isdir(os.path.join(self.projects_path, d))])
    
    def get_bugs_for_project(self, project_name):
        """Get all bugs for a project"""
        bugs_path = os.path.join(self.projects_path, project_name, "bugs")
        if not os.path.exists(bugs_path):
            return []
        return sorted([d for d in os.listdir(bugs_path) 
                      if os.path.isdir(os.path.join(bugs_path, d)) and d.isdigit()], 
                      key=int)
    
    def read_bug_info(self, project_name, bug_id):
        """Read bug.info file"""
        bug_info_path = os.path.join(self.projects_path, project_name, "bugs", 
                                      bug_id, "bug.info")
        if not os.path.exists(bug_info_path):
            return None
        
        bug_info = {}
        with open(bug_info_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    bug_info[key.strip()] = value.strip().strip('"')
        return bug_info
    
    def read_bug_patch(self, project_name, bug_id):
        
        patch_path = os.path.join(self.projects_path, project_name, "bugs", 
                                   bug_id, "bug_patch.txt")
        if not os.path.exists(patch_path):
            return None
        
        with open(patch_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    
    def is_code_line(self, line):
        
        stripped = line.strip()
        
        if not stripped:
            return False
        if stripped.startswith('#'):
            return False
        return True
    
    def is_single_line_bug(self, patch_content):

        if not patch_content:
            return False, None
        
        lines = patch_content.split('\n')
        changed_files = []
        current_file = None
        
        
        for line in lines:
            if line.startswith('diff --git'):
                match = re.search(r'b/(.+)$', line)
                if match:
                    file_path = match.group(1)
                    
                    if file_path.endswith('.py') and 'test' not in file_path.lower():
                        changed_files.append(file_path)
        
        
        if len(changed_files) != 1:
            return False, None
        
        
        file_path = changed_files[0]
        added_code_lines = []
        deleted_code_lines = []
        
        for line in lines:
            
            if line.startswith('-') and not line.startswith('---'):
                code = line[1:]
                if self.is_code_line(code):
                    deleted_code_lines.append(code.strip())
            
            elif line.startswith('+') and not line.startswith('+++'):
                code = line[1:]
                if self.is_code_line(code):
                    added_code_lines.append(code.strip())
        
        
        if len(deleted_code_lines) == 1 and len(added_code_lines) == 1:
            return True, {
                'file': file_path,
                'deleted': deleted_code_lines[0],
                'added': added_code_lines[0]
            }
        
        return False, None
    
    def parse_patch(self, patch_content):
        """Parse patch file to extract bug information"""
        if not patch_content:
            return []
        
        bugs_info = []
        lines = patch_content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            
            if line.startswith('diff --git'):
                file_info = self.extract_file_info(lines, i)
                if file_info:
                    bugs_info.append(file_info)
                    i = file_info['end_index']
                else:
                    i += 1
            else:
                i += 1
        
        return bugs_info
    
    def extract_file_info(self, lines, start_idx):
        """Extract detailed info for a single file from patch"""
        
        diff_line = lines[start_idx]
        match = re.search(r'b/(.+)$', diff_line)
        if not match:
            return None
        
        file_path = match.group(1)
        file_name = os.path.basename(file_path)
        
        
        if not file_name.endswith('.py'):
            return None
        
        file_info = {
            'buggy_file_name': file_name,
            'buggy_file_path': file_path,
            'buggy_line_locations': [],
            'changed_functions': [],
            'end_index': start_idx + 1
        }
        
        i = start_idx + 1
        current_function = None
        function_before_lines = []
        function_after_lines = []
        in_function = False
        
        while i < len(lines):
            line = lines[i]
            
            
            if line.startswith('diff --git'):
                file_info['end_index'] = i
                break
            
            
            if line.startswith('@@'):
                match = re.search(r'@@\s+-(\d+),?\d*\s+\+(\d+),?\d*\s+@@(.*)$', line)
                if match:
                    old_start = int(match.group(1))
                    new_start = int(match.group(2))
                    context = match.group(3).strip()
                    
                    
                    if 'def ' in context:
                        
                        if current_function and (function_before_lines or function_after_lines):
                            file_info['changed_functions'].append({
                                'buggy_function_name': current_function,
                                'function_before': '\n'.join(function_before_lines),
                                'function_after': '\n'.join(function_after_lines)
                            })
                        
                        
                        func_match = re.search(r'def\s+(\w+)\s*\(', context)
                        if func_match:
                            current_function = func_match.group(1)
                            function_before_lines = []
                            function_after_lines = []
                            in_function = True
                        else:
                            current_function = None
                            in_function = False
                    
                    file_info['buggy_line_locations'].append(old_start)
            
            
            elif line.startswith('-') and not line.startswith('---'):
                
                if in_function:
                    function_before_lines.append(line[1:])
                    
            elif line.startswith('+') and not line.startswith('+++'):
                
                if in_function:
                    function_after_lines.append(line[1:])
                    
            elif line.startswith(' ') and in_function:
                
                function_before_lines.append(line[1:])
                function_after_lines.append(line[1:])
            
            i += 1
        
        
        if current_function and (function_before_lines or function_after_lines):
            file_info['changed_functions'].append({
                'buggy_function_name': current_function,
                'function_before': '\n'.join(function_before_lines),
                'function_after': '\n'.join(function_after_lines)
            })
        
        file_info['end_index'] = i
        
        
        file_info['buggy_line_locations'] = sorted(set(file_info['buggy_line_locations']))
        
        return file_info
    
    def analyze_bug(self, project_name, bug_id):
        """Analyze a single bug"""
        
        bug_info = self.read_bug_info(project_name, bug_id)
        if not bug_info:
            return None
        
        
        patch_content = self.read_bug_patch(project_name, bug_id)
        if not patch_content:
            return None
        
        
        is_single_line, single_line_info = self.is_single_line_bug(patch_content)
        if not is_single_line:
            return None
        
        parsed_files = self.parse_patch(patch_content)
        if not parsed_files:
            return None
        
        
        bug_data = {
            'project': project_name,
            'bug_id': bug_id,
            'single_line_change': single_line_info,
            'bug_description': {
                'python_version': bug_info.get('python_version', ''),
                'buggy_commit_id': bug_info.get('buggy_commit_id', ''),
                'fixed_commit_id': bug_info.get('fixed_commit_id', ''),
                'test_file': bug_info.get('test_file', ''),
                'github_url': bug_info.get('github_url', '')
            },
            'files': parsed_files
        }
        
        return bug_data
    
    def save_bug_data(self, bug_data):
        """Save bug data to JSON file"""
        project_name = bug_data['project']
        bug_id = bug_data['bug_id']
        
        
        output_dir = os.path.join(self.output_base, project_name)
        os.makedirs(output_dir, exist_ok=True)
        
        
        output_file = os.path.join(output_dir, f"bug_{bug_id}.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(bug_data, f, indent=2, ensure_ascii=False)
        
        return output_file
    
    def analyze_all_bugs(self, max_bugs_per_project=None):
        """Analyze all bugs in BugsInPy (only single-line bugs)"""
        projects = self.get_all_projects()
        
        print(f"Found {len(projects)} projects")
        print("="*80)
        print("Filtering for single-line bugs only...")
        print("="*80)
        
        total_bugs = 0
        project_stats = {}
        
        for idx, project in enumerate(projects, 1):
            print(f"\n[{idx}/{len(projects)}] Processing: {project}")
            
            bugs = self.get_bugs_for_project(project)
            if not bugs:
                print(f"  No bugs found")
                continue
            
            print(f"  Checking {len(bugs)} bugs...")
            
            
            bugs_to_process = bugs[:max_bugs_per_project] if max_bugs_per_project else bugs
            
            single_line_count = 0
            for bug_id in bugs_to_process:
                bug_data = self.analyze_bug(project, bug_id)
                
                if bug_data:
                    output_file = self.save_bug_data(bug_data)
                    total_bugs += 1
                    single_line_count += 1
                    
                    
                    files_count = len(bug_data['files'])
                    functions_count = sum(len(f['changed_functions']) for f in bug_data['files'])
                    print(f"    ✓ Bug {bug_id}: Single-line bug → {output_file}")
            
            if single_line_count > 0:
                project_stats[project] = single_line_count
                print(f"  → Found {single_line_count} single-line bugs in {project}")
        
        print(f"\n{'='*80}")
        print(f"SINGLE-LINE BUG SUMMARY")
        print(f"{'='*80}")
        print(f"Total single-line bugs found: {total_bugs}")
        print(f"\nBreakdown by project:")
        for project, count in sorted(project_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  {project}: {count} bugs")
        print(f"\n{'='*80}")
        print(f"✓ Data saved in '{self.output_base}/' directory")
        print(f"{'='*80}")
        
        return project_stats



if __name__ == "__main__":
    BUGSINPY_PATH = "./BugsInPy"
    
    if not os.path.exists(BUGSINPY_PATH):
        print(f"Error: BugsInPy not found at {BUGSINPY_PATH}")
        exit(1)
    
    analyzer = BugsInPyAnalyzer(BUGSINPY_PATH)
    
    print("BugsInPy Analyzer")
    
    print("Extracting single-line bugs following paper criteria:")
    print("  - Only one non-test Python file changed")
    print("  - Exactly 1 line deleted and 1 line added (excluding blanks/comments)")
    
    
    
    stats = analyzer.analyze_all_bugs(max_bugs_per_project=None)