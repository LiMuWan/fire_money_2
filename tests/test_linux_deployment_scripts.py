from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LINUX_SCRIPTS = ROOT / "scripts" / "linux"


class LinuxDeploymentScriptsTest(unittest.TestCase):
    def test_systemd_services_are_single_purpose_and_auto_restart(self) -> None:
        preview = (LINUX_SCRIPTS / "firemoney-preview.service").read_text(encoding="utf-8")
        beta = (LINUX_SCRIPTS / "firemoney-beta-watch.service").read_text(encoding="utf-8")

        self.assertIn("EnvironmentFile=-/etc/firemoney/firemoney.env", preview)
        self.assertIn("EnvironmentFile=-/etc/firemoney/firemoney.env", beta)
        self.assertIn("ExecStart=/opt/firemoney/scripts/linux/start_firemoney_preview.sh", preview)
        self.assertIn("ExecStart=/opt/firemoney/scripts/linux/start_firemoney_beta_watch.sh", beta)
        self.assertIn("Restart=always", preview)
        self.assertIn("Restart=always", beta)
        self.assertIn("WantedBy=multi-user.target", preview)
        self.assertIn("WantedBy=multi-user.target", beta)

    def test_start_scripts_use_flock_and_repo_local_venv(self) -> None:
        preview = (LINUX_SCRIPTS / "start_firemoney_preview.sh").read_text(encoding="utf-8")
        beta = (LINUX_SCRIPTS / "start_firemoney_beta_watch.sh").read_text(encoding="utf-8")

        self.assertIn("flock -n", preview)
        self.assertIn("flock -n", beta)
        self.assertIn("FIREMONEY_APP_DIR:-/opt/firemoney", preview)
        self.assertIn("FIREMONEY_APP_DIR:-/opt/firemoney", beta)
        self.assertIn(".venv/bin/python", preview)
        self.assertIn(".venv/bin/python", beta)
        self.assertIn("client.desktop.firemoney_client.preview", preview)
        self.assertIn("beta-start", beta)
        self.assertIn("--loop", beta)

    def test_installer_keeps_secrets_out_of_repo_and_enables_services(self) -> None:
        installer = (LINUX_SCRIPTS / "install_firemoney_systemd.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("/etc/firemoney", installer)
        self.assertIn("chmod 0600 \"$ENV_FILE\"", installer)
        self.assertIn("python3 -m ensurepip --version", installer)
        self.assertIn("apt-get install -y python3-venv python3-pip", installer)
        self.assertIn("rm -rf \"$APP_DIR/.venv\"", installer)
        self.assertIn("FEISHU_ENABLED=false", installer)
        self.assertIn("# FEISHU_WEBHOOK_URL=", installer)
        self.assertIn("systemctl enable firemoney-preview.service", installer)
        self.assertIn("systemctl enable firemoney-beta-watch.service", installer)

    def test_health_check_covers_http_single_port_and_schedule_health(self) -> None:
        health = (LINUX_SCRIPTS / "check_firemoney_server.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("systemctl --no-pager --plain status firemoney-preview.service", health)
        self.assertIn("ss -ltnp", health)
        self.assertIn("curl -fsS", health)
        self.assertIn("grep -q \"FireMoney\"", health)
        self.assertIn("schedule-health --brief", health)

    def test_windows_runtime_check_covers_beta_watch_loop(self) -> None:
        script = (ROOT / "scripts" / "check_firemoney_runtime.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("Get-BetaWatchProcesses", script)
        self.assertIn("client\\.desktop\\.firemoney_client\\.one_to_two_cli", script)
        self.assertIn("beta-start", script)
        self.assertIn("--loop", script)
        self.assertIn("Test-NamedMutexHeld", script)
        self.assertIn("beta_watch_missing", script)

    def test_windows_deploy_script_requires_key_and_never_accepts_password(self) -> None:
        script = (ROOT / "scripts" / "deploy_tencent_ubuntu.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("[string]$KeyPath", script)
        self.assertIn("scp.exe", script)
        self.assertIn("ssh.exe", script)
        self.assertIn("install_firemoney_systemd.sh", script)
        self.assertNotIn("Password", script)
        self.assertNotIn("sshpass", script)


if __name__ == "__main__":
    unittest.main()
