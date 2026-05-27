"""
Tests for Web Integrity — ensures static resources exist, no unsafe inline scripts are in auth pages,
and forms have proper 'name' attributes to avoid regressions on blocks (e.g., Ermes/CSPs).
"""

import os
import re
import pytest

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

AUTH_HTML_FILES = [
    "login.html",
    "register.html",
    "forgot-password.html",
    "reset-password.html"
]

def test_static_scripts_exist():
    """Verify that all local scripts referenced in HTML files actually exist on disk."""
    assert os.path.isdir(STATIC_DIR), "Static directory does not exist!"

    # Regex to find <script src="...">
    script_src_regex = re.compile(r'<script\s+[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)

    html_files = [f for f in os.listdir(STATIC_DIR) if f.endswith(".html")]
    assert len(html_files) > 0, "No HTML files found in static folder!"

    for filename in html_files:
        filepath = os.path.join(STATIC_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        matches = script_src_regex.findall(content)
        for src in matches:
            # Skip dynamic/runtime interpolated scripts
            if "$" in src or "{" in src or "}" in src:
                continue

            # We only check local static files (e.g. /static/login.js or static/login.js)
            # and ignore external libraries (e.g. iubenda)
            if "/static/" in src or src.startswith("static/") or (not src.startswith("http") and not src.startswith("//")):
                # Normalize path (remove query params like ?v=...)
                clean_src = src.split("?")[0]
                # Extract filename cleanly (stripping leading slashes and prefix 'static/')
                basename = clean_src.lstrip("/").replace("static/", "")
                target_path = os.path.join(STATIC_DIR, basename)

                assert os.path.isfile(target_path), (
                    f"HTML file '{filename}' references missing local script: '{src}' "
                    f"(resolved to '{target_path}'). This will cause a 404 in production!"
                )


def test_no_inline_scripts_in_auth_pages():
    """Ensure auth pages do not contain inline <script> tags to bypass CSP/Ermes blockages."""
    inline_script_regex = re.compile(r'<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)

    for filename in AUTH_HTML_FILES:
        filepath = os.path.join(STATIC_DIR, filename)
        assert os.path.isfile(filepath), f"Missing auth page: {filename}"

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        matches = inline_script_regex.findall(content)
        for script_body in matches:
            # Strip whitespace
            cleaned_body = script_body.strip()
            # Allow completely empty scripts if any, but fail if they contain actual logic
            assert len(cleaned_body) == 0, (
                f"Security regression in '{filename}': Found unsafe inline script block!\n"
                f"Content: {cleaned_body[:100]}...\n"
                f"All Javascript must be externalized to dedicated .js files to bypass CSP/Ermes security blocks."
            )


def test_form_inputs_have_name_attributes():
    """Ensure all critical inputs (email, password) in auth forms have a 'name' attribute for native fallback integrity."""
    input_regex = re.compile(r'<input\s+([^>]+)>', re.IGNORECASE)

    for filename in AUTH_HTML_FILES:
        filepath = os.path.join(STATIC_DIR, filename)
        assert os.path.isfile(filepath), f"Missing auth page: {filename}"

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        inputs = input_regex.findall(content)
        for input_attrs in inputs:
            # We only care about email and password fields
            if 'type="email"' in input_attrs or "type='email'" in input_attrs or \
               'type="password"' in input_attrs or "type='password'" in input_attrs:
                # Check for 'name='
                has_name = 'name=' in input_attrs or "name=" in input_attrs
                assert has_name, (
                    f"Regression in '{filename}': Input field '{input_attrs.strip()}' "
                    f"is missing the 'name' attribute. Standard HTML form fallback will fail!"
                )
