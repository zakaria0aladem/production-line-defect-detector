from pathlib import Path

import yaml

# Folder of this repository, so paths work no matter where the script is started from
BASE_DIR = Path(__file__).resolve().parent


def load_settings(path=None):
    path = Path(path) if path else BASE_DIR / "settings.yaml"
    if not path.is_absolute():
        path = BASE_DIR / path

    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Copy settings.example.yaml to settings.yaml and fill in your values."
        )

    with open(path, encoding="utf-8") as f:
        settings = yaml.safe_load(f)

    # model path is relative to the repository folder
    model = Path(settings["model"])
    if not model.is_absolute():
        settings["model"] = str(BASE_DIR / model)

    return settings
