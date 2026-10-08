import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "deploy" / "install.sh"
SERVICE = ROOT / "deploy" / "lensmind.service"


def test_install_script_is_valid_bash() -> None:
    subprocess.run(["bash", "-n", str(INSTALL)], check=True)


def test_install_script_covers_the_documented_steps() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    for needed in [
        "python3-venv python3-dev build-essential pkg-config libgphoto2-dev gphoto2",
        '"$REPO_DIR[pi]"',
        "usermod -aG plugdev",
        "/etc/lensmind.env",
        "LENSMIND_PORT=80",
        "systemctl enable --now lensmind.service",
    ]:
        assert needed in text


def test_service_unit() -> None:
    text = SERVICE.read_text(encoding="utf-8")
    for line in [
        "User=@USER@",
        "WorkingDirectory=@REPO@",
        "EnvironmentFile=/etc/lensmind.env",
        "ExecStart=@REPO@/.venv/bin/lensmind",
        "AmbientCapabilities=CAP_NET_BIND_SERVICE",
        "Restart=on-failure",
    ]:
        assert line in text
