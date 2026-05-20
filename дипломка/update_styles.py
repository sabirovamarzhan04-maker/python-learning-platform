import os
import re

html_files = [
    "index.html",
    "materials.html",
    "practice.html",
    "results.html",
    "quiz.html",
    "profile.html",
    "all_results.html"
]

base_dir = r"c:\Users\user\Downloads\дипломка\дипломка"

for file in html_files:
    path = os.path.join(base_dir, file)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Replace the entire <style> block
        new_content = re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="style.css" />', content, flags=re.DOTALL)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {file}")
