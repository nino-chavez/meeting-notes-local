// swift-tools-version:5.9
import PackageDescription

let package = Package(
  name: "aec-probe",
  platforms: [.macOS(.v13)],
  targets: [
    .executableTarget(name: "aec-probe", path: "Sources/aec-probe")
  ]
)
