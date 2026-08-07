// swift-tools-version:5.9
import PackageDescription

let package = Package(
  name: "permission-probe",
  platforms: [.macOS(.v13)],
  targets: [
    .executableTarget(name: "permission-probe", path: "Sources/permission-probe")
  ]
)
