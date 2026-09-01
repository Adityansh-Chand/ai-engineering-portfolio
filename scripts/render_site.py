"""Generate `index.html` from `scripts/site_facts.json`.

The landing page is the first thing a reviewer sees and it was the last thing
anyone checked. It drifted for months against hand-typed numbers: five services
each claiming **"accuracy 1.0"** — the circular evaluations the entire rebuild
existed to remove — alongside test counts an order of magnitude low, a retired
HR-policy corpus, a deleted hash-bucket embedder described as current, and a
"no screenshots are committed yet" notice sitting above fifteen committed
assets. Nothing caught it, because CI's only assertion about the page was that
`README.md` was non-empty.

The failure was structural, not clerical. Numbers baked into markup, with no
generator and no check, will drift the moment anything moves. So the facts now
live in one JSON file, the page is generated from it, and CI regenerates the
page to confirm the committed HTML still matches. Editing `index.html` by hand
now fails the build.

    python scripts/render_site.py            # regenerate index.html
    python scripts/render_site.py --check    # fail if committed HTML differs
    python scripts/render_site.py --refresh  # re-count tests from sibling repos

`--check` needs nothing but this repository, so it runs in CI. `--refresh` reads
the five sibling repositories to re-count tests, so it runs locally -- the same
split as the load test and the cost model.
"""
import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
FACTS_PATH = ROOT / "scripts" / "site_facts.json"
OUTPUT_PATH = ROOT / "index.html"

OWNER = "Adityansh-Chand"
INDEX_REPO = "ai-engineering-portfolio"


def repo_url(repo):
    return f"https://github.com/{OWNER}/{repo}"


def blob(path):
    return f"https://github.com/{OWNER}/{INDEX_REPO}/blob/main/{path}"


def link(url):
    """Facts may carry a bare doc path or a full URL. Both must work."""
    return url if url.startswith("http") else blob(url)


def head(facts):
    totals = facts["totals"]
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta
      name="description"
      content="A reviewer guide to five interconnected AI services and an agent that drives them, where every claim is measured on a held-out split and the results that came out worse than hoped are published too."
    >
    <title>AI Engineering Portfolio</title>
    <link rel="stylesheet" href="styles.css">
  </head>
  <body>
    <header class="site-header" id="top">
      <nav class="nav" aria-label="Primary navigation">
        <a class="brand" href="#top" aria-label="AI Engineering Portfolio home">
          <span class="brand-mark" aria-hidden="true">A</span>
          <span>AI Engineering Portfolio</span>
        </a>
        <div class="nav-links">
          <a href="#evidence">Evidence</a>
          <a href="#matrix">Matrix</a>
          <a href="#projects">Projects</a>
          <a href="#review-path">Review path</a>
          <a href="#docs">Docs</a>
        </div>
      </nav>

      <section class="hero" aria-labelledby="hero-title">
        <p class="eyebrow">Five interconnected services, independently runnable</p>
        <h1 id="hero-title">Every claim measured. The bad results published too.</h1>
        <p class="hero-copy">
          Five AI services, each solving a different problem, plus an agent that
          drives all five as tools. Each runs standalone with its own fitted
          model and API, and they compose into one system through enrichment
          edges that degrade rather than fail. Every number below is measured on
          a held-out split and reproduced by CI &mdash; including the ones that
          came out worse than hoped.
        </p>
        <div class="hero-actions" aria-label="Primary links">
          <a class="button primary" href="#evidence">See the evidence</a>
          <a class="button" href="#matrix">Project matrix</a>
          <a class="button" href="{blob('docs/WALKTHROUGH.md')}">Interviewer walkthrough</a>
        </div>
        <dl class="signal-strip" aria-label="Portfolio highlights">
          <div><dt>{totals['services']}</dt><dd>Interconnected services</dd></div>
          <div><dt>{totals['tests']}</dt><dd>Tests</dd></div>
          <div><dt>{totals['real_data_tracks']}</dt><dd>Validated on real public data</dd></div>
          <div><dt>{totals['adrs']}</dt><dd>Decision records</dd></div>
        </dl>
      </section>
    </header>

    <main>
"""


def evidence_section(facts):
    cards = []
    for item in facts["evidence"]:
        cards.append(f"""          <article class="path-card">
            <h3>{item['title']}</h3>
            <p>{item['body']}</p>
            <p><a href="{link(item['doc'])}">Read the measurement</a> &middot;
               <a href="{blob('docs/assets/' + item['asset'])}">evidence asset</a></p>
          </article>""")
    return f"""      <section class="section" id="evidence" aria-labelledby="evidence-title">
        <div class="section-heading">
          <p class="eyebrow">What the measurements say</p>
          <h2 id="evidence-title">The findings worth reading first.</h2>
        </div>
        <div class="path-grid">
{chr(10).join(cards)}
        </div>
      </section>

"""


def matrix_section(facts):
    rows = []
    for service in facts["services"]:
        rows.append(f"""              <tr>
                <th scope="row"><a href="{repo_url(service['repo'])}">{service['short']}</a></th>
                <td>{service['problem']}</td>
                <td>{service['headline']}</td>
                <td>{service['real_data']}</td>
                <td>{service['tests']}</td>
                <td><code>:{service['port']}</code></td>
              </tr>""")
    return f"""      <section class="section" id="matrix" aria-labelledby="matrix-title">
        <div class="section-heading">
          <p class="eyebrow">Project matrix</p>
          <h2 id="matrix-title">What each system measures.</h2>
        </div>
        <p class="hero-copy">
          Bring the whole stack up with <code>docker compose up</code> from this
          repository; each service is then on the port shown. To run one alone,
          clone its repository and follow its <code>DEMO.md</code>.
        </p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Project</th>
                <th scope="col">Problem</th>
                <th scope="col">Headline result</th>
                <th scope="col">Real-data track</th>
                <th scope="col">Tests</th>
                <th scope="col">Compose port</th>
              </tr>
            </thead>
            <tbody>
{chr(10).join(rows)}
            </tbody>
          </table>
        </div>
      </section>

"""


def projects_section(facts):
    articles = []
    for service in facts["services"]:
        articles.append(f"""        <article class="project-detail" id="{service['id']}">
          <div class="project-title-row">
            <h3>{service['name']}</h3>
            <a href="{repo_url(service['repo'])}">Repository</a>
          </div>
          <dl>
            <div><dt>Problem</dt><dd>{service['problem']}</dd></div>
            <div><dt>How it works</dt><dd>{service['architecture']}</dd></div>
            <div><dt>Headline result</dt><dd>{service['headline']}</dd></div>
            <div><dt>Validated on real data</dt><dd>{service['real_data']}</dd></div>
            <div><dt>What came out worse than hoped</dt><dd>{service['negative']}</dd></div>
            <div><dt>API surface</dt><dd>{service['endpoints']} &mdash; see <a href="{repo_url(service['repo'])}/blob/main/DEMO.md">DEMO.md</a>.</dd></div>
            <div><dt>Tests</dt><dd>{service['tests']}, run by CI on every push, which also regenerates the datasets and retrains to prove the committed metrics.</dd></div>
            <div><dt>Known limits</dt><dd>{service['gaps']}</dd></div>
          </dl>
        </article>""")
    return f"""      <section class="section" id="projects" aria-labelledby="projects-title">
        <div class="section-heading">
          <p class="eyebrow">Deep dives</p>
          <h2 id="projects-title">One section per service, linked to the runnable repository.</h2>
        </div>

{chr(10).join(articles)}
      </section>

"""


def review_path_section(facts):
    return f"""      <section class="section" id="review-path" aria-labelledby="review-path-title">
        <div class="section-heading">
          <p class="eyebrow">Reviewer path</p>
          <h2 id="review-path-title">Three minutes, fifteen, or thirty.</h2>
        </div>
        <div class="path-grid">
          <article class="path-card">
            <h3>3 minutes</h3>
            <ol>
              <li>Read the evidence cards above.</li>
              <li>Scan the project matrix for headline results and real-data tracks.</li>
              <li>Open one <a href="{blob('docs/adr')}">decision record</a> &mdash; they carry the alternatives that were rejected.</li>
            </ol>
          </article>
          <article class="path-card">
            <h3>15 minutes</h3>
            <ol>
              <li>Start with Enterprise RAG or Incident Detection &mdash; both publish a result that went against them.</li>
              <li>Compare each README's headline against its model card.</li>
              <li>Read <a href="{blob('docs/SCALE_TEST.md')}">SCALE_TEST.md</a> for a finding that a later measurement overturned.</li>
            </ol>
          </article>
          <article class="path-card">
            <h3>30 minutes, running it</h3>
            <ol>
              <li><code>docker compose up</code> from this repository brings all five up.</li>
              <li>Or clone one repo, then <code>pytest -q</code>, its training script with <code>--verify</code>, and its evaluation script.</li>
              <li><code>python scripts/verify_contracts.py --local</code> checks the cross-service contracts against live services.</li>
            </ol>
          </article>
        </div>
      </section>

"""


def badges_section(facts):
    badges = []
    for service in facts["services"]:
        url = repo_url(service["repo"])
        badges.append(f"""          <a href="{url}/actions/workflows/ci.yml">
            <span>{service['short']}</span>
            <img src="{url}/actions/workflows/ci.yml/badge.svg" alt="{service['short']} CI status">
          </a>""")
    return f"""      <section class="section" aria-labelledby="badge-title">
        <div class="section-heading">
          <p class="eyebrow">CI evidence</p>
          <h2 id="badge-title">Every repository retrains and re-evaluates on push.</h2>
        </div>
        <div class="badge-grid" aria-label="GitHub Actions status badges">
{chr(10).join(badges)}
        </div>
      </section>

"""


def docs_section(facts):
    entries = []
    for doc in facts["docs"]:
        entries.append(f"""          <a href="{doc['url']}"><strong>{doc['title']}</strong><span>{doc['note']}</span></a>""")
    return f"""      <section class="section" id="docs" aria-labelledby="docs-title">
        <div class="section-heading">
          <p class="eyebrow">Documentation map</p>
          <h2 id="docs-title">From overview to evidence.</h2>
        </div>
        <div class="docs-grid">
{chr(10).join(entries)}
        </div>
      </section>

"""


def boundaries_section(facts):
    items = "".join(f"            <li>{line}</li>\n" for line in facts["boundaries"])
    return f"""      <section class="section" aria-labelledby="boundaries-title">
        <div class="section-heading">
          <p class="eyebrow">What this does not claim</p>
          <h2 id="boundaries-title">Worth knowing before going deep.</h2>
        </div>
        <div class="deploy-panel">
          <ol>
{items}          </ol>
        </div>
      </section>

"""


def tail(facts):
    return f"""    </main>

    <footer class="site-footer">
      <p>
        Index for five interconnected AI services and an agent over them.
        This page is generated from <code>scripts/site_facts.json</code> by
        <code>scripts/render_site.py</code>, and CI regenerates it to check the
        numbers here still match the repositories. Facts refreshed
        {facts['refreshed_on']}.
      </p>
      <a href="#top">Back to top</a>
    </footer>
  </body>
</html>
"""


def render(facts):
    return (
        head(facts)
        + evidence_section(facts)
        + matrix_section(facts)
        + projects_section(facts)
        + review_path_section(facts)
        + badges_section(facts)
        + docs_section(facts)
        + boundaries_section(facts)
        + tail(facts)
    )


def count_tests(repo):
    """Collected test count for a sibling repository, or None if unavailable."""
    path = WORKSPACE / repo
    if not path.exists():
        return None
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            capture_output=True, text=True, cwd=str(path), timeout=600,
        )
    except Exception:  # noqa: BLE001
        return None
    match = re.search(r"^(\d+) tests? collected", result.stdout, re.M)
    return int(match.group(1)) if match else None


def refresh(facts):
    """Re-count tests and ADRs from disk. Local only -- CI has one repo."""
    total = 0
    for service in facts["services"]:
        counted = count_tests(service["repo"])
        if counted is None:
            print(f"  {service['repo']}: could not count, keeping "
                  f"{service['tests']}")
            total += service["tests"]
            continue
        if counted != service["tests"]:
            print(f"  {service['repo']}: {service['tests']} -> {counted}")
            service["tests"] = counted
        total += counted
    facts["totals"]["tests"] = total

    adrs = len(list((ROOT / "docs" / "adr").glob("0*.md")))
    for repo in (service["repo"] for service in facts["services"]):
        adrs += len(list((WORKSPACE / repo / "docs" / "adr").glob("0*.md")))
    if adrs != facts["totals"]["adrs"]:
        print(f"  ADRs: {facts['totals']['adrs']} -> {adrs}")
        facts["totals"]["adrs"] = adrs

    print(f"  totals: {total} tests, {adrs} decision records")
    return facts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed index.html differs")
    parser.add_argument("--refresh", action="store_true",
                        help="re-count tests and ADRs from the sibling repos")
    args = parser.parse_args()

    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))

    if args.refresh:
        print("refreshing counts from disk:")
        facts = refresh(facts)
        FACTS_PATH.write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
        print(f"facts -> {FACTS_PATH.relative_to(ROOT)}")

    rendered = render(facts)

    if args.check:
        committed = OUTPUT_PATH.read_text(encoding="utf-8")
        if committed != rendered:
            print("index.html does not match scripts/site_facts.json.")
            print("The page is generated -- edit the facts file and run:")
            print("  python scripts/render_site.py")
            raise SystemExit(1)
        totals = facts["totals"]
        print(f"index.html matches site_facts.json: {totals['services']} services, "
              f"{totals['tests']} tests, {totals['adrs']} decision records")
        return

    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"index.html <- scripts/site_facts.json "
          f"({len(rendered.splitlines())} lines)")


if __name__ == "__main__":
    main()
