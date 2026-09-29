"""Build, smoke-test without network, and save an offline ECUME delivery.

Requires Python 3.10+ and Docker with Linux containers on the connected machine.
The target machine only needs Docker Engine and Docker Compose v2.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, capture: bool = False, timeout: int | None = None) -> str:
    result = subprocess.run(args, check=True, text=True, capture_output=capture,
                            cwd=ROOT, timeout=timeout)
    return result.stdout.strip() if capture else ""


HTTP_HELPER = """
import json, os, urllib.request
def request(path, data=None, method=None):
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request('http://127.0.0.1:8080' + path, data=payload,
        headers={'Content-Type':'application/json'}, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)
"""

SMOKE_SETUP = HTTP_HELPER + """
from html.parser import HTMLParser
from rdflib import Graph
from pyshacl import validate
assert os.geteuid() != 0, 'Container must not run as root'
assert request('/api/health') == {'status':'ok'}
assert request('/api/documents') == [], 'Image must not contain user documents'
with urllib.request.urlopen('http://127.0.0.1:8080/') as response:
    html = response.read().decode()
assert 'id="root"' in html
class Assets(HTMLParser):
    urls = []
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('src', 'href') and value:
                assert not value.startswith(('http:', 'https:', '//')), value
                if value.startswith('/assets/'):
                    self.urls.append(value)
parser = Assets()
parser.feed(html)
assert parser.urls, 'Built assets missing'
for url in parser.urls:
    with urllib.request.urlopen('http://127.0.0.1:8080' + url) as response:
        assert response.read(), url
validate(Graph(), shacl_graph=Graph(), inference='none', do_owl_imports=False)
settings = request('/api/admin/llm')
settings['ollama_model'] = 'ecume-offline-smoke-only'
request('/api/admin/llm', settings, 'PUT')
node = request('/api/graph/nodes', {'label':'Container smoke check', 'type':'object'})
archive = request('/api/export/json?scope=all')
assert node['id'] in json.dumps(archive)
print(json.dumps({'node_id':node['id']}))
"""


def smoke_test(image: str, platform: str) -> None:
    name = "ecume-smoke-" + uuid.uuid4().hex[:12]
    volume = name + "-data"

    def start() -> None:
        run("docker", "run", "--detach", "--name", name, "--platform", platform,
            "--pull=never", "--network=none", "--read-only", "--tmpfs", "/tmp:mode=1777",
            "--cap-drop=ALL", "--security-opt", "no-new-privileges:true",
            "--mount", f"type=volume,src={volume},dst=/data", image, capture=True)
        for _ in range(45):
            try:
                run("docker", "exec", name, "python", "-c", HTTP_HELPER +
                    "assert request('/api/health')['status'] == 'ok'", capture=True, timeout=15)
                return
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                time.sleep(2)
        raise RuntimeError("Container health did not become ready within the smoke-test deadline.")

    try:
        run("docker", "volume", "create", volume, capture=True)
        start()
        state = json.loads(run("docker", "exec", name, "python", "-c", SMOKE_SETUP,
                               capture=True, timeout=60))
        run("docker", "rm", "--force", name, capture=True)
        start()
        verify = HTTP_HELPER + (
            "assert request('/api/admin/llm')['ollama_model'] == 'ecume-offline-smoke-only'\n"
            f"assert {state['node_id']!r} in json.dumps(request('/api/graph?scope=all'))\n"
        )
        run("docker", "exec", name, "python", "-c", verify, capture=True, timeout=30)
        print("Smoke test passed: offline UI/API, SHACL, exports, persistent data and settings.")
    except Exception:
        subprocess.run(["docker", "logs", "--tail", "60", name], check=False)
        raise
    finally:
        # Names are generated here; no existing application container/volume is touched.
        subprocess.run(["docker", "rm", "--force", name], check=False, capture_output=True)
        subprocess.run(["docker", "volume", "rm", volume], check=False, capture_output=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_delivery(output: Path, image: str, platform: str, image_id: str) -> None:
    shutil.copy2(ROOT / "deploy" / "compose.yaml", output / "compose.yaml")
    template = (ROOT / "deploy" / ".env.example").read_text(encoding="utf-8")
    (output / ".env.example").write_text(template.replace("ECUME_IMAGE=ecume:offline", f"ECUME_IMAGE={image}"), encoding="utf-8")
    shutil.copy2(ROOT / "docs" / "deploiement-hors-ligne.md", output / "README.md")
    try:
        revision = run("git", "rev-parse", "HEAD", capture=True)
        dirty = bool(run("git", "status", "--porcelain", capture=True))
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = "unknown", True
    files = {path.name: sha256(path) for path in sorted(output.iterdir()) if path.is_file()}
    (output / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in files.items()), encoding="ascii")
    (output / "manifest.json").write_text(json.dumps({
        "image": image, "image_id": image_id, "platform": platform,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_revision": revision, "working_tree_dirty": dirty,
        "network_disabled_smoke_test": "passed", "contains_llm_model": False,
        "files_sha256": files,
    }, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="ecume:offline")
    parser.add_argument("--platform", choices=("linux/amd64", "linux/arm64"), default="linux/amd64")
    parser.add_argument("--output", type=Path, default=ROOT / "dist-offline" / "ecume-offline")
    args = parser.parse_args()
    if not args.image or args.image.startswith("-") or any(char.isspace() for char in args.image):
        parser.error("Invalid image tag.")
    if args.output.exists():
        parser.error("Output already exists. Choose a new directory; nothing will be overwritten.")
    if not shutil.which("docker"):
        parser.error("Docker is missing. Install/start Docker with Linux containers on the connected machine.")
    if run("docker", "info", "--format", "{{.OSType}}", capture=True) != "linux":
        parser.error("Docker must use Linux containers.")
    run("docker", "compose", "--env-file", "deploy/.env.example", "-f", "deploy/compose.yaml", "config", "--quiet")
    run("docker", "build", "--pull", "--platform", args.platform, "--tag", args.image, ".")
    smoke_test(args.image, args.platform)
    image_id = run("docker", "image", "inspect", "--format", "{{.Id}}", args.image, capture=True)
    args.output.mkdir(parents=True)
    run("docker", "image", "save", "--output", str(args.output.resolve() / "ecume-image.tar"), args.image)
    write_delivery(args.output, args.image, args.platform, image_id)
    print(f"Offline delivery ready: {args.output.resolve()}")
    print("Transfer the entire directory. No database, user files, API keys or LLM model are included.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"Packaging failed: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr, file=sys.stderr)
        sys.exit(1)
