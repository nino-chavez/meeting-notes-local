from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


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
        first_mutating_sign = signing.index("codesign --force --options runtime")
        app_submit = signing.index('notarytool submit "$STAGE/app.zip"')
        app_staple = signing.index('stapler staple "$APP"')
        dmg_build = signing.index('build-dmg.sh" "$APP" "$DMG"')
        dmg_submit = signing.index('notarytool submit "$DMG"')
        final_verify = signing.index('verify-signed-release.sh" "$APP" "$DMG"')
        self.assertLess(unsigned_verify, first_mutating_sign)
        self.assertLess(app_submit, app_staple)
        self.assertLess(app_staple, dmg_build)
        self.assertLess(dmg_build, dmg_submit)
        self.assertLess(dmg_submit, final_verify)

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

    def test_bundle_verifier_refuses_boundary_runtime_and_extra_entitlements(self) -> None:
        verifier = source("scripts/verify-release-bundle.py")
        for required in (
            'manifest.get("admission") == "product"',
            "NSMicrophoneUsageDescription",
            "NSAudioCaptureUsageDescription",
            'EXPECTED_TEAM_ID = "34VZ63G58M"',
            'arches.stdout.strip().split() == ["arm64"]',
            "np.linalg.svd(np.eye(2))",
            "np.fft.fft(np.ones(4))",
            "not entitlements(path)",
        ):
            self.assertIn(required, verifier)


if __name__ == "__main__":
    unittest.main()
