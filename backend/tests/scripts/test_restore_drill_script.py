import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RESTORE_SCRIPT = PROJECT_ROOT / "scripts" / "ops" / "restore-drill.ps1"


def _run_restore_script(backup_path: Path, target_database: str) -> subprocess.CompletedProcess[str]:
    escaped_script = str(RESTORE_SCRIPT).replace("'", "''")
    escaped_backup = str(backup_path).replace("'", "''")
    command = (
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); "
        "$password = ConvertTo-SecureString 'test-only' -AsPlainText -Force; "
        f"& '{escaped_script}' -BackupPath '{escaped_backup}' "
        f"-TargetDatabase '{target_database}' -DatabasePassword $password -Confirm:$false"
    )
    return subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _write_manifest(backup_path: Path, *, checksum: str) -> None:
    manifest = {
        "schema_version": "postgres-backup-manifest/v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": "agent_platform",
        "dump_file": backup_path.name,
        "dump_bytes": backup_path.stat().st_size,
        "dump_sha256": checksum,
        "alembic_version": "u8f9a0b1c2d3",
        "public_table_count": 1,
        "critical_table_counts": {},
    }
    backup_path.with_suffix(backup_path.suffix + ".manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )


def test_restore_drill_rejects_checksum_mismatch_before_database_access(tmp_path: Path) -> None:
    backup_path = tmp_path / "corrupt.dump"
    backup_path.write_bytes(b"not a PostgreSQL dump")
    _write_manifest(backup_path, checksum="0" * 64)

    result = _run_restore_script(backup_path, "agent_platform_restore_script_test")

    assert result.returncode != 0
    assert "Backup checksum does not match its manifest." in (
        result.stdout + result.stderr
    )


def test_restore_drill_rejects_application_database_before_database_access(
    tmp_path: Path,
) -> None:
    backup_path = tmp_path / "valid-integrity.dump"
    contents = b"integrity only; no database command should run"
    backup_path.write_bytes(contents)
    _write_manifest(backup_path, checksum=hashlib.sha256(contents).hexdigest())

    result = _run_restore_script(backup_path, "agent_platform")

    assert result.returncode != 0
    assert "Restore drill may not target an application database." in (
        result.stdout + result.stderr
    )
