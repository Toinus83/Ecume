import importlib.util
from pathlib import Path


def checker():
    path = Path(__file__).resolve().parents[2] / 'scripts/check-python-deps.py'
    spec = importlib.util.spec_from_file_location('ecume_dependency_check',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_runtime_dependencies_present():
    module = checker()
    assert module.missing(Path(__file__).resolve().parents[1] / 'requirements.txt')==[]


def test_missing_package_detected_without_installation(monkeypatch):
    module = checker()
    def unavailable(name):
        if name.lower()=='rdflib':
            raise module.PackageNotFoundError(name)
        return '999.0'
    monkeypatch.setattr(module,'version',unavailable)
    missing = module.missing(Path(__file__).resolve().parents[1] / 'requirements.txt')
    assert 'rdflib==7.6.0' in missing


def test_dev_includes_runtime_requirements():
    module = checker()
    requirements = list(module.requirements(Path(__file__).resolve().parents[1] / 'requirements-dev.txt'))
    assert {'rdflib','defusedxml','pytest'} <= {item.name.lower() for item in requirements}
