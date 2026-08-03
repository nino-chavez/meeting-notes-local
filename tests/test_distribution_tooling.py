from __future__ import annotations

import json
import importlib.util
import plistlib
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def load_release_verifier():
    path = ROOT / "scripts/verify-release-bundle.py"
    spec = importlib.util.spec_from_file_location("release_bundle_verifier", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DistributionToolingTests(unittest.TestCase):
    def test_dmg_builder_and_layout_are_closed(self) -> None:
        builder = source("scripts/build-dmg.sh")
        for required in (
            "ditto",
            "ln -s /Applications",
            "-format UDZO",
            '[[ "$DMG" == *.dmg ]]',
        ):
            self.assertIn(required, builder)

        layout = source("scripts/verify-dmg-layout.sh")
        for required in (
            "-readonly -nobrowse",
            "Contents/Info.plist",
            '[[ -L "$MOUNT/Applications" ]]',
            'readlink "$MOUNT/Applications"',
            "unexpected top-level DMG content",
        ):
            self.assertIn(required, layout)

    def test_signing_sequence_reuses_the_proven_film_room_trust_path(self) -> None:
        signing = source("scripts/sign-notarize.sh")
        self.assertIn('PROFILE="filmroom-notary"', signing)
        self.assertIn('EXPECTED_TEAM_ID="34VZ63G58M"', signing)
        identity_check = signing.index("Developer ID Application identity:")
        notary_check = signing.index("notary profile:")
        preflight_verdict = signing.index("signing preflight: PASS")
        self.assertLess(identity_check, preflight_verdict)
        self.assertLess(notary_check, preflight_verdict)

        unsigned_verify = signing.index('verify-release-bundle.py" "$APP"')
        first_mutating_sign = signing.index('codesign "${sign_args[@]}" "$path"')
        manifest_refresh = signing.index(
            'build_manifest.py" \\\n  "$APP/Contents/Resources" --admission "$ADMISSION"'
        )
        outer_app_sign = signing.index(
            'codesign --force --options runtime --timestamp \\\n'
            '  --entitlements "$CAPTURE_ENTITLEMENTS" --sign "$IDENTITY" "$APP"'
        )
        app_submit = signing.index('notarytool submit "$STAGE/app.zip"')
        app_staple = signing.index('stapler staple "$APP"')
        dmg_build = signing.index('build-dmg.sh" "$APP" "$DMG"')
        dmg_submit = signing.index('notarytool submit "$DMG"')
        final_verify = signing.index('verify-signed-release.sh" "$APP" "$DMG"')
        self.assertLess(unsigned_verify, first_mutating_sign)
        self.assertLess(first_mutating_sign, manifest_refresh)
        self.assertLess(manifest_refresh, outer_app_sign)
        self.assertLess(app_submit, app_staple)
        self.assertLess(app_staple, dmg_build)
        self.assertLess(dmg_build, dmg_submit)
        self.assertLess(dmg_submit, final_verify)

        self.assertIn('if [[ "$cmd" == "run-alpha" ]]', signing)
        self.assertIn('--entitlements "$PYTHON_ENTITLEMENTS"', signing)
        self.assertIn('EXPECTED_IDENTIFIER="com.ninochavez.local-meeting-notes"', signing)
        self.assertIn('PYTHON_SIGNING_IDENTIFIER="${EXPECTED_IDENTIFIER}.python-runtime"', signing)
        self.assertIn('--identifier "$PYTHON_SIGNING_IDENTIFIER"', signing)
        self.assertIn('--entitlements "$CAPTURE_ENTITLEMENTS"', signing)

        entitlements = plistlib.loads(
            (ROOT / "apps/desktop/src-tauri/python-entitlements.plist").read_bytes()
        )
        self.assertEqual(
            entitlements,
            {"com.apple.security.cs.allow-unsigned-executable-memory": True},
        )
        capture_entitlements = plistlib.loads(
            (ROOT / "apps/desktop/src-tauri/capture-entitlements.plist").read_bytes()
        )
        self.assertEqual(
            capture_entitlements,
            {"com.apple.security.device.audio-input": True},
        )

    def test_frozen_verifier_covers_app_dmg_layout_and_runtime(self) -> None:
        verifier = source("scripts/verify-signed-release.sh")
        for required in (
            'codesign --verify --deep --strict "$APP"',
            'stapler validate "$APP"',
            'spctl --assess --type execute --verbose=4 "$APP"',
            'codesign --verify --strict "$DMG"',
            'stapler validate "$DMG"',
            "context:primary-signature",
            "verify-dmg-layout.sh",
            'verify-release-bundle.py" "$APP" --signed',
            'shasum -a 256 "$DMG"',
        ):
            self.assertIn(required, verifier)

    def test_bundle_verifier_refuses_unselected_admission_and_extra_entitlements(self) -> None:
        verifier = source("scripts/verify-release-bundle.py")
        for required in (
            'manifest.get("admission") == admission',
            'choices=("product", "internal-alpha")',
            'default="product"',
            '"whisper-large-v3-turbo-weights"',
            '"bin/meeting-capture"',
            "NSMicrophoneUsageDescription",
            "NSAudioCaptureUsageDescription",
            'EXPECTED_TEAM_ID = "34VZ63G58M"',
            '"arm64" in architecture_set',
            'architecture_set <= {"arm64", "x86_64"}',
            'if "executable" in kind.stdout',
            "np.linalg.svd(np.eye(2))",
            "np.fft.fft(np.ones(4))",
            "entitlements(path) == expected_entitlements",
            "CAPTURE_EXECUTABLE",
            '"com.apple.security.device.audio-input": True',
            'EXPECTED_PYTHON_IDENTIFIER = f"{EXPECTED_IDENTIFIER}.python-runtime"',
            "CODE_SIGNATURE_RUNTIME = 0x00010000",
            "expected_designated_requirement(identifier)",
            "entitlements(app) == CAPTURE_ENTITLEMENTS",
            "verify_forbidden_note_runtime_resources_absent(resources)",
            "FORBIDDEN_NOTE_RUNTIME_RESOURCES",
            'Path("note-bridge.py")',
            '"note-runtime-project.json"',
            '"note-validator.zip"',
        ):
            self.assertIn(required, verifier)

    def test_note_project_runtime_manifest_and_validator_zip_are_generated_canonically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = {
                "python-runtime/bin/python3.12": b"runtime",
                "worker/main.py": b"worker",
                "bin/audiotee": b"tap",
                "encoder-unavailable.identity": b"encoder",
                "note-bridge.py": source("worker/note_bridge.py").encode(),
            }
            for relative, contents in fixtures.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(contents)
            completed = subprocess.run(
                [str(ROOT / "worker/build_manifest.py"), str(root)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            raw = (root / "note-runtime-project.json").read_bytes()
            document = json.loads(raw)
            self.assertEqual(
                raw,
                json.dumps(document, ensure_ascii=False, indent=2).encode(),
            )
            self.assertEqual(list(document), [
                "schema", "role", "runtime", "bridge", "validator", "generator", "models"
            ])
            self.assertEqual(document["schema"], "note-runtime/1")
            self.assertEqual(document["role"], "project")
            self.assertIsNone(document["generator"])
            self.assertEqual(document["models"], [])
            self.assertEqual(document["bridge"]["relative_path"], "note-bridge.py")
            self.assertEqual(document["validator"]["relative_path"], "note-validator.zip")
            with zipfile.ZipFile(root / "note-validator.zip") as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["note_validator.py", "summarize.py", "transcript.py", "capture_health.py"],
                )

    def test_bundle_contract_excludes_unadmitted_note_project_runtime(self) -> None:
        forbidden = {
            "../runtime/note-bridge.py",
            "../runtime/note-runtime-project.json",
            "../runtime/note-validator.zip",
        }
        for config_path in (
            "apps/desktop/src-tauri/tauri.conf.json",
            "apps/desktop/src-tauri/tauri.preview.conf.json",
        ):
            resources = json.loads(source(config_path))["bundle"]["resources"]
            self.assertTrue(forbidden.isdisjoint(resources), config_path)

        preview_preparer = source("scripts/prepare-preview-bundle.sh")
        self.assertIn("require_note_runtime_absent", preview_preparer)
        self.assertIn('[[ ! -e "$path" && ! -L "$path" ]]', preview_preparer)
        for name in forbidden:
            self.assertIn(name.removeprefix("../runtime/"), preview_preparer)

    def test_bundle_manifest_rebuild_excludes_and_refuses_note_runtime_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = {
                "python-runtime/bin/python3.12": b"runtime",
                "worker/main.py": b"worker",
                "bin/meeting-capture": b"tap",
                "encoder-unavailable.identity": b"encoder",
                "models/whisper-large-v3-turbo/config.json": b"config",
                "models/whisper-large-v3-turbo/weights.safetensors": b"weights",
            }
            for relative, contents in fixtures.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(contents)
            completed = subprocess.run(
                [
                    str(ROOT / "worker/build_manifest.py"),
                    str(root),
                    "--admission",
                    "internal-alpha",
                    "--exclude-note-runtime",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((root / "app-runtime.json").is_file())
            for name in (
                "note-bridge.py",
                "note-runtime-project.json",
                "note-validator.zip",
            ):
                self.assertFalse((root / name).exists(), name)

            forbidden = root / "note-bridge.py"
            forbidden.write_bytes(b"unadmitted")
            blocked = subprocess.run(
                [
                    str(ROOT / "worker/build_manifest.py"),
                    str(root),
                    "--admission",
                    "internal-alpha",
                    "--exclude-note-runtime",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("test-only note runtime resource is present", blocked.stderr)

    def test_release_verifier_requires_note_runtime_resources_to_be_absent(self) -> None:
        verifier = load_release_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            resources = Path(temporary)
            verifier.verify_forbidden_note_runtime_resources_absent(resources)
            for relative in verifier.FORBIDDEN_NOTE_RUNTIME_RESOURCES:
                path = resources / relative
                path.write_bytes(b"unadmitted")
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify_forbidden_note_runtime_resources_absent(resources)
                path.unlink()

            broken_link = resources / verifier.FORBIDDEN_NOTE_RUNTIME_RESOURCES[0]
            broken_link.symlink_to("missing-test-only-runtime")
            with self.assertRaises(verifier.VerificationError):
                verifier.verify_forbidden_note_runtime_resources_absent(resources)

    def test_release_identifiers_have_the_exact_developer_id_requirement_relationship(self) -> None:
        verifier = load_release_verifier()
        outer = verifier.expected_designated_requirement(verifier.EXPECTED_IDENTIFIER)
        nested = verifier.expected_designated_requirement(
            verifier.EXPECTED_PYTHON_IDENTIFIER
        )
        self.assertEqual(
            verifier.EXPECTED_PYTHON_IDENTIFIER,
            f"{verifier.EXPECTED_IDENTIFIER}.python-runtime",
        )
        self.assertEqual(
            nested,
            outer.replace(verifier.EXPECTED_IDENTIFIER, verifier.EXPECTED_PYTHON_IDENTIFIER),
        )
        self.assertEqual(
            verifier.normalized_requirement(nested.replace(" exists", " /* exists */")),
            nested,
        )

    def test_frozen_alpha_verification_selects_alpha_admission(self) -> None:
        runbook = source("docs/distribution-runbook.md")
        frozen = runbook.split("## Recheck a frozen artifact", 1)[1]
        self.assertIn(
            '"target/release/bundle/macos/Local-Meeting-Notes-<version>-macos-arm64.dmg" \\\n  internal-alpha',
            frozen,
        )


if __name__ == "__main__":
    unittest.main()
