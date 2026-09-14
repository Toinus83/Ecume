"""Check installed distributions against the project's requirements without installing."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys

from pip._vendor.packaging.requirements import Requirement


def requirements(path: Path, visited: set[Path] | None = None):
    visited = set() if visited is None else visited
    path = path.resolve()
    if path in visited:
        return
    visited.add(path)
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('-r '):
            yield from requirements(path.parent / line[3:].strip(), visited)
        else:
            requirement = Requirement(line)
            if not requirement.marker or requirement.marker.evaluate():
                yield requirement


def missing(path: Path) -> list[str]:
    result = []
    for requirement in requirements(path):
        try:
            installed = version(requirement.name)
        except PackageNotFoundError:
            result.append(str(requirement))
            continue
        if installed not in requirement.specifier:
            result.append(str(requirement))
    return result


if __name__ == '__main__':
    absent = missing(Path(sys.argv[1]))
    if absent:
        print('Dependances a installer ou ajuster : '+', '.join(absent))
        raise SystemExit(1)
    print('Toutes les dependances Python demandees sont deja presentes.')
