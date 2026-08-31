"""Render real command output into SVG terminal cards.

The capture guide asked for GIFs. This produces SVGs instead, and the reason is
not that GIFs were unavailable:

- an SVG is **text**, so it diffs in review and a reviewer can see that the output
  was not edited
- it regenerates from the commands themselves, so it cannot drift from what the
  code actually prints -- a stale GIF is indistinguishable from a current one
- it is a few KB rather than a few MB, and stays crisp at any size

The trade is that a still cannot show timing or interactivity. For evidence that
a pipeline produces a given result that does not matter; for a UI demo it would.

Output is captured from **real runs**. Nothing here is typed by hand, which is the
entire point: an asset that can be hand-edited is not evidence.

The landing site is captured as a real PNG instead, because there a screenshot IS
the evidence -- layout, type and spacing are the thing being shown, and rendering
them as text would be a description rather than a capture.

    python scripts/capture_assets.py            # cards and screenshots
    python scripts/capture_assets.py --list     # what would be captured
"""
import argparse
import html
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
ASSETS = ROOT / "docs" / "assets"

# Values that change per run and would make every capture a diff. Replaced with a
# stable placeholder so the SVGs only change when the OUTPUT changes.
VOLATILE = [
    (re.compile(r"\bdemo-[0-9a-f]{8}\b"), "demo-1a2b3c4d"),
    (re.compile(r"\btrace-[0-9a-f-]{8,}\b"), "trace-1a2b3c4d"),
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"), "2026-08-31 09:00:00"),
    (re.compile(r"\bin \d+\.\d+s\b"), "in 0.00s"),
    (re.compile(r"\b\d+\.\d+ MB\b"), "0.0 MB"),
]

FOREGROUND = "#d8dee9"
BACKGROUND = "#20242c"
ACCENT = "#8fbcbb"
DIM = "#6f7787"
LINE_HEIGHT = 19
CHAR_WIDTH = 8.4
PADDING = 18


def stabilise(text):
    for pattern, replacement in VOLATILE:
        text = pattern.sub(replacement, text)
    # A published asset should not carry whoever-ran-it's home directory, and a
    # repo-relative path is what a reader would type anyway.
    text = re.sub(re.escape(str(WORKSPACE)) + r"[\\/][\w.-]+[\\/]", "", text)
    return text.replace("\\", "/")


def render(title, command, output, path):
    lines = [line.rstrip() for line in output.splitlines()]
    # A card taller than this stops being readable in a README.
    if len(lines) > 46:
        lines = lines[:22] + ["  ...", f"  ({len(lines) - 44} lines omitted)", "  ..."] + lines[-20:]

    width = max([len(line) for line in lines] + [len(command) + 2, len(title)]) + 4
    pixel_width = int(width * CHAR_WIDTH) + PADDING * 2
    pixel_height = (len(lines) + 4) * LINE_HEIGHT + PADDING * 2

    rows = []
    y = PADDING + LINE_HEIGHT * 2
    rows.append(
        f'<text x="{PADDING}" y="{PADDING + LINE_HEIGHT // 2 + 4}" '
        f'fill="{DIM}" font-size="12">{html.escape(title)}</text>'
    )
    rows.append(
        f'<text x="{PADDING}" y="{y}" fill="{ACCENT}">'
        f'$ {html.escape(command)}</text>'
    )
    for line in lines:
        y += LINE_HEIGHT
        rows.append(
            f'<text x="{PADDING}" y="{y}" fill="{FOREGROUND}">'
            f'{html.escape(line)}</text>'
        )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{pixel_width}" height="{pixel_height}"
     viewBox="0 0 {pixel_width} {pixel_height}" role="img"
     aria-label="{html.escape(title)}">
  <rect width="100%" height="100%" rx="8" fill="{BACKGROUND}"/>
  <g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
     font-size="13" xml:space="preserve">
{chr(10).join("    " + row for row in rows)}
  </g>
</svg>
'''
    path.write_text(svg, encoding="utf-8")
    return len(lines)


# Headless Chrome or Edge, whichever the machine has. Both accept the same flags.
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "google-chrome", "chromium", "chromium-browser",
]

# Desktop only, deliberately.
#
# A phone-width capture was attempted and dropped. Headless Chrome's
# `--window-size` sets the window but does not apply mobile viewport emulation, so
# it lays the page out at desktop width and crops -- producing an image of a
# broken-looking site. The site is not broken: driven through a real browser at
# 375px the page reports `scrollWidth == clientWidth`, no horizontal overflow, and
# the only elements extending past the viewport are table cells inside their
# `overflow-x: auto` container, which is the intended behaviour.
#
# Publishing that image would have been worse than publishing none. Proper mobile
# capture needs device emulation over the DevTools protocol, which is a dependency
# this script does not justify for one asset.
SCREENSHOTS = [
    {"name": "landing-site", "width": 1280, "height": 900,
     "title": "The static landing site"},
]


def find_browser():
    for candidate in BROWSERS:
        path = Path(candidate)
        if path.exists():
            return str(path)
        found = shutil.which(candidate)
        if found:
            return found
    return None


def screenshot(browser, url, path, width, height):
    """Render a page to PNG. Returns False rather than raising when it cannot.

    --virtual-time-budget waits for fonts and layout to settle; without it the
    capture can land mid-render and show unstyled text, which looks like a broken
    site rather than a timing artefact.
    """
    result = subprocess.run(
        [browser, "--headless", "--disable-gpu", "--hide-scrollbars",
         "--virtual-time-budget=6000", f"--window-size={width},{height}",
         f"--screenshot={path}", url],
        capture_output=True, text=True, timeout=180,
    )
    return path.exists() and path.stat().st_size > 0


def run(command, cwd, timeout=900, env=None):
    result = subprocess.run(
        command, cwd=str(cwd), capture_output=True, text=True,
        timeout=timeout, shell=False,
    )
    return (result.stdout + result.stderr).strip()


CAPTURES = [
    {
        "name": "end-to-end-demo",
        "title": "Five services, one request id, six acts",
        "display": "python scripts/demo_end_to_end.py --local",
        "argv": [sys.executable, "scripts/demo_end_to_end.py", "--local"],
        "cwd": ROOT,
    },
    {
        "name": "contract-verification",
        "title": "Consumer-driven contracts, verified against live services",
        "display": "python scripts/verify_contracts.py --local",
        "argv": [sys.executable, "scripts/verify_contracts.py", "--local"],
        "cwd": ROOT,
    },
    {
        "name": "retrieval-bench",
        "title": "Retrieval compared on BEIR/NFCorpus (human relevance judgments)",
        "display": "python evaluation/harness.py --beir nfcorpus",
        "argv": [sys.executable, "evaluation/harness.py", "--beir", "nfcorpus"],
        "cwd": WORKSPACE / "enterprise-rag-knowledge-system",
    },
    {
        "name": "incident-real-data",
        "title": "Anomaly detection on real telemetry: the fitted model loses",
        "display": "python training/train_real.py",
        "argv": [sys.executable, "training/train_real.py"],
        "cwd": WORKSPACE / "ai-incident-detection-platform",
    },
    {
        "name": "sales-real-data",
        "title": "Evaluation design is worth more than the leaky feature",
        "display": "python training/train_real.py",
        "argv": [sys.executable, "training/train_real.py"],
        "cwd": WORKSPACE / "ai-sales-intelligence-engine",
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--only", help="capture one by name")
    args = parser.parse_args()

    if args.list:
        for capture in CAPTURES:
            print(f"{capture['name']:24} {capture['display']}")
        for shot in SCREENSHOTS:
            print(f"{shot['name']:24} screenshot {shot['width']}x{shot['height']}")
        return 0

    ASSETS.mkdir(parents=True, exist_ok=True)
    for capture in CAPTURES:
        if args.only and capture["name"] != args.only:
            continue
        if not Path(capture["cwd"]).exists():
            print(f"SKIP {capture['name']}: {capture['cwd']} not present")
            continue

        print(f"capturing {capture['name']} ...", flush=True)
        output = stabilise(run(capture["argv"], capture["cwd"]))
        path = ASSETS / f"{capture['name']}.svg"
        lines = render(capture["title"], capture["display"], output, path)
        print(f"  {path.relative_to(ROOT)}  ({lines} lines, "
              f"{path.stat().st_size / 1024:.1f} KB)")

    browser = find_browser()
    if browser is None:
        # Said out loud: a missing screenshot must not look like a page that
        # failed to render.
        print("no Chrome or Edge found; screenshots SKIPPED (the SVG cards above "
              "are unaffected)")
        return 0

    # The local file, not the deployed site: this captures the repository as it
    # stands, so the image cannot be newer or older than the code beside it.
    url = (ROOT / "index.html").resolve().as_uri()
    for shot in SCREENSHOTS:
        if args.only and shot["name"] != args.only:
            continue
        path = ASSETS / f"{shot['name']}.png"
        print(f"capturing {shot['name']} ...", flush=True)
        if screenshot(browser, url, path, shot["width"], shot["height"]):
            print(f"  {path.relative_to(ROOT)}  "
                  f"({shot['width']}x{shot['height']}, "
                  f"{path.stat().st_size / 1024:.1f} KB)")
        else:
            print(f"  FAILED to capture {shot['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
