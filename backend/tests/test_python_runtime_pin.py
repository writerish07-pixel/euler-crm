"""Railway Python pin: pymongo 4.5 C extensions abort on Railpack's default 3.13."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).resolve().parents[1]


def _requirement_pins():
    pins = {}
    for line in (BACKEND / "requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" in line:
            name, ver = line.split("==", 1)
            pins[name.strip().lower()] = ver.strip()
    return pins


def test_python_version_file_pins_3_12():
    text = (ROOT / ".python-version").read_text().strip()
    assert text.startswith("3.12"), text


def test_runtime_txt_pins_3_12():
    text = (ROOT / "runtime.txt").read_text().strip()
    assert text == "python-3.12", text


def test_pymongo_and_motor_support_python_313():
    pins = _requirement_pins()
    pymongo = tuple(int(p) for p in pins["pymongo"].split(".")[:2])
    motor = tuple(int(p) for p in pins["motor"].split(".")[:2])
    assert pymongo >= (4, 9), pins["pymongo"]
    assert motor >= (3, 6), pins["motor"]
