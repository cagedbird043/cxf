#!/usr/bin/env python3
"""Update the homebrew formula version and sha256 checksums for cxf."""
import re
import sys

formula_path = sys.argv[1]
version = sys.argv[2]
sha_linux = sys.argv[3]
sha_darwin_arm = sys.argv[4]

with open(formula_path) as f:
    content = f.read()

# Update version
content = re.sub(r'version ".*"', f'version "{version}"', content)

# Update sha256 based on URL patterns (sha256 line follows url line for each platform)
platforms = [
    ('cxf-darwin-arm64', sha_darwin_arm),
    ('cxf-linux-amd64', sha_linux),
]

for url_suffix, new_sha in platforms:
    pattern = re.escape(f'{url_suffix}"')
    url_match = re.search(pattern, content)
    if url_match:
        after_url = content[url_match.end():]
        sha_line_match = re.search(r'sha256 "[^"]*"', after_url)
        if sha_line_match:
            old_sha = sha_line_match.group()
            new = f'sha256 "{new_sha}"'
            content = content.replace(old_sha, new, 1)

with open(formula_path, 'w') as f:
    f.write(content)

print(f"Updated {formula_path} to version {version}")
