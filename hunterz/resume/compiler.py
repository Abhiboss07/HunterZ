"""Local PDF compiler for tailored resumes using system tools (pdflatex, tectonic, or headless Chrome)."""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def find_latex_compiler() -> Optional[str]:
    """Check for local tectonic, pdflatex, or xelatex."""
    for tool in ["tectonic", "pdflatex", "xelatex"]:
        path = shutil.which(tool)
        if path:
            return path
    return None


def find_chrome() -> Optional[str]:
    """Check for local google-chrome or chromium."""
    candidates = [
        "/home/abhiboss/.local/bin/google-chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chrome")
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def compile_tex_to_pdf(tex_path: Path, output_dir: Path) -> Optional[Path]:
    """
    Compile a .tex file to PDF locally.
    Returns path to compiled PDF if successful, else None.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    compiler = find_latex_compiler()

    if compiler:
        tool_name = Path(compiler).name
        try:
            if "tectonic" in tool_name:
                cmd = [compiler, str(tex_path), "-o", str(output_dir)]
            else:
                cmd = [compiler, "-interaction=nonstopmode", f"-output-directory={output_dir}", str(tex_path)]

            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            expected_pdf = output_dir / f"{tex_path.stem}.pdf"
            if proc.returncode == 0 and expected_pdf.exists():
                return expected_pdf
        except Exception as e:
            print(f"LaTeX compile warning: {e}")

    return None


def compile_html_to_pdf(html_path: Path, output_pdf_path: Path) -> bool:
    """
    Compile an HTML resume to PDF using the local Google Chrome headless engine.
    Ensures 100% local, zero-leak PDF compilation even when LaTeX packages are missing.
    """
    chrome = find_chrome()
    if not chrome:
        return False

    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={output_pdf_path.resolve()}",
        str(html_path.resolve())
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        return output_pdf_path.exists() and output_pdf_path.stat().st_size > 0
    except Exception as e:
        print(f"Headless Chrome PDF error: {e}")
        return False
