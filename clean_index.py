import re
import os

file_path = r'c:\Users\Emmanuel_PC\Track2Train\Track2Train-staging\templates\index.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Spaced braces and over-bracing normalization
# Replace any sequence of { and spaces with {{
content = re.sub(r'\{[\s\{]*\{', '{{', content)
# Replace any sequence of } and spaces with }}
content = re.sub(r'\}[\s\}]*\}', '}}', content)

# 2. Specifically normalize loop.index0 tags
# This collapses {{ loop.index0 }} and variations into a clean {{ loop.index0 }}
content = re.sub(r'\{\{\s*loop\.index0\s*\}\}', '{{ loop.index0 }}', content)

# 3. Consolidate fragmented variables like const name{{ loop.index0 }} = ...
# This targets cases where braces were added between the variable name and the loop index
content = re.sub(r'(const\s+[\w]+)\{\{\s*loop\.index0\s*\}\}\s*=?', r'\1{{ loop.index0 }} =', content)

# 4. Remove redundant logic blocks that isolation variable declarations
# e.g. { const x{{ loop.index0 }} } } = ...
content = re.sub(r'\{?\s*(const\s+[\w]+\{\{\s*loop\.index0\s*\}\})\s*\}*\s*=', r'\1 =', content)

# 5. Fix common data injection splits
content = re.sub(r'=\s*\{\{\s*(act\.[\w\_]+)\s*\|\s*safe\s*\}\}\s*;?', r'= {{ \1 | safe }};', content)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Robust cleanup complete.")
