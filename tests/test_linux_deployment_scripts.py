from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LINUX_SCRIPTS = ROOT / "scripts" / "linux"


class LinuxDeploymentScriptsTest(unittest.TestCase):
    def test_linux_scripts_are_forced_to_lf_by_gitattributes(self) -> None:
        attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")

        self.assertIn("scripts/linux/* text eol=lf", attrs)

    def test_systemd_services_are_single_purpose_and_auto_restart(self) -> None:
        preview = (LINUX_SCRIPTS / "firemoney-preview.service").read_text(encoding="utf-8")
        beta = (LINUX_SCRIPTS / "firemoney-beta-watch.service").read_text(encoding="utf-8")

        self.assertIn("EnvironmentFile=-/etc/firemoney/firemoney.env", preview)
        self.assertIn("EnvironmentFile=-/etc/firemoney/firemoney.env", beta)
        self.assertIn("ExecStart=/opt/firemoney/scripts/linux/start_firemoney_preview.sh", preview)
        self.assertIn("ExecStart=/opt/firemoney/scripts/linux/start_firemoney_beta_watch.sh", beta)
        self.assertIn("Restart=always", preview)
        self.assertIn("Restart=on-failure", beta)
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
        self.assertIn("refresh_firemoney_preview.sh", preview)
        self.assertIn("beta-start", beta)
        self.assertIn("--loop", beta)

    def test_preview_start_script_serves_http_before_refreshing_content(self) -> None:
        preview = (LINUX_SCRIPTS / "start_firemoney_preview.sh").read_text(encoding="utf-8")

        self.assertIn("FIREMONEY_PREVIEW_REFRESH_INTERVAL_SECONDS", preview)
        self.assertIn("refresh_firemoney_preview.sh", preview)
        self.assertIn("exec \"$PYTHON\" -B scripts/linux/firemoney_preview_server.py", preview)
        self.assertIn("scripts/linux/firemoney_preview_server.py", preview)
        self.assertLess(
            preview.index("refresh_firemoney_preview.sh"),
            preview.index("scripts/linux/firemoney_preview_server.py"),
        )

    def test_preview_refresh_script_updates_html_and_runtime_status(self) -> None:
        refresh = (LINUX_SCRIPTS / "refresh_firemoney_preview.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("client.desktop.firemoney_client.preview", refresh)
        self.assertIn("schedule-health --brief", refresh)
        self.assertIn("paper-db --brief", refresh)
        self.assertIn("paper_json_raw", refresh)
        self.assertIn("closed_trade_count", refresh)
        self.assertIn("runtime_status.json", refresh)
        self.assertIn("auto_refreshed_preview", refresh)
        self.assertIn("firemoney_preview_refresh.log", refresh)
        self.assertIn("preview_refresh_failed", refresh)
        self.assertIn("今日禁止参考旧指挥单", refresh)
        self.assertIn("schedule_health_status", refresh)
        self.assertIn("schedule_health_blocked", refresh)

    def test_installer_keeps_secrets_out_of_repo_and_enables_services(self) -> None:
        installer = (LINUX_SCRIPTS / "install_firemoney_systemd.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("/etc/firemoney", installer)
        self.assertIn("chmod 0600 \"$ENV_FILE\"", installer)
        self.assertIn("python3 -m ensurepip --version", installer)
        self.assertIn("apt-get install -y python3-venv python3-pip", installer)
        self.assertIn("sha256sum \"$REQ_FILE\"", installer)
        self.assertIn("Python dependencies unchanged", installer)
        self.assertIn("rm -rf \"$VENV_DIR\"", installer)
        self.assertIn("FEISHU_ENABLED=false", installer)
        self.assertIn("# FEISHU_WEBHOOK_URL=", installer)
        self.assertIn("refresh_firemoney_preview.sh", installer)
        self.assertIn("run_firemoney_cli_with_env.sh", installer)
        self.assertIn("import_firemoney_env.sh", installer)
        self.assertIn("systemctl enable firemoney-preview.service", installer)
        self.assertIn("systemctl enable firemoney-beta-watch.service", installer)

    def test_linux_cli_env_helper_preserves_secrets_without_root_owned_runtime(self) -> None:
        helper = (LINUX_SCRIPTS / "run_firemoney_cli_with_env.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("/etc/firemoney/firemoney.env", helper)
        self.assertIn("set -a", helper)
        self.assertIn("sudo --preserve-env", helper)
        self.assertIn("-u \"$SERVICE_USER\"", helper)
        self.assertIn("one_to_two_cli", helper)
        self.assertIn("FEISHU_APP_SECRET", helper)

    def test_linux_import_env_helper_only_merges_feishu_keys(self) -> None:
        helper = (LINUX_SCRIPTS / "import_firemoney_env.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("FEISHU_ENABLED", helper)
        self.assertIn("FEISHU_APP_SECRET", helper)
        self.assertIn("allowed_keys", helper)
        self.assertIn("chmod 0600", helper)
        self.assertIn("updated_keys=", helper)
        self.assertNotIn("FIREMONEY_PYTHON", helper)

    def test_health_check_covers_http_single_port_and_schedule_health(self) -> None:
        health = (LINUX_SCRIPTS / "check_firemoney_server.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("FIREMONEY_APP_DIR:-/opt/firemoney", health)
        self.assertIn("cd \"$APP_DIR\"", health)
        self.assertIn("systemctl is-active firemoney-preview.service", health)
        self.assertIn("firemoney-beta-watch.service: $BETA_STATE", health)
        self.assertIn("systemctl --no-pager --plain status firemoney-preview.service", health)
        self.assertIn("ss -ltnp", health)
        self.assertIn("curl -fsS", health)
        self.assertIn("2>/dev/null", health)
        self.assertIn("FIREMONEY_HEALTH_WAIT_SECONDS", health)
        self.assertIn("preview_http_timeout", health)
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
        self.assertIn("[string]$FeishuEnvPath", script)
        self.assertIn("scp.exe", script)
        self.assertIn("ssh.exe", script)
        self.assertIn("install_firemoney_systemd.sh", script)
        self.assertIn("import_firemoney_env.sh", script)
        self.assertIn("run_firemoney_cli_with_env.sh' beta-check", script)
        self.assertIn("Stopping FireMoney services before upload", script)
        self.assertIn("systemctl stop firemoney-beta-watch.service firemoney-preview.service", script)
        self.assertIn("systemctl reset-failed firemoney-beta-watch.service", script)
        self.assertIn("--exclude=client/desktop/preview/*.html", script)
        self.assertIn("--exclude=client/desktop/preview/*.json", script)
        self.assertIn("rm -f '$RemoteDir/client/desktop/preview/'*.html", script)
        self.assertIn("ConvertFrom-Json", script)
        self.assertIn("$BetaCheckReady", script)
        self.assertIn("systemctl stop firemoney-beta-watch", script)
        self.assertNotIn("Password", script)
        self.assertNotIn("sshpass", script)

    def test_windows_one_click_deploy_auto_discovers_local_feishu_env(self) -> None:
        script = (ROOT / "scripts" / "deploy_tencent_ubuntu_one_click.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("[string]$FeishuEnvPath", script)
        self.assertIn(".firemoney", script)
        self.assertIn("feishu.env", script)
        self.assertIn("-FeishuEnvPath", script)

    def test_preview_generator_uses_atomic_write(self) -> None:
        preview = (ROOT / "client" / "desktop" / "firemoney_client" / "preview.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def _atomic_write_text", preview)
        self.assertIn("NamedTemporaryFile", preview)
        self.assertIn("os.replace", preview)
        self.assertIn("_atomic_write_text(", preview)


if __name__ == "__main__":
    unittest.main()
