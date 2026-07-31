// swift-tools-version: 5.9
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
  name: "audiotee",
  platforms: [
    .macOS("14.2")
  ],
  products: [
    // Library that can be imported by other packages
    .library(
      name: "AudioTeeCore",
      targets: ["AudioTeeCore"]
    ),
    // CLI executable
    .executable(
      name: "audiotee",
      targets: ["AudioTeeCLI"]
    ),
    .executable(
      name: "meeting-capture",
      targets: ["MeetingCaptureCLI"]
    ),
    .executable(
      name: "meeting-capture-self-test",
      targets: ["MeetingCaptureSelfTest"]
    ),
  ],
  targets: [
    // Core library with all business logic
    .target(
      name: "AudioTeeCore",
      path: "Sources/AudioTeeCore"
    ),

    // CLI executable that uses the library
    .executableTarget(
      name: "AudioTeeCLI",
      dependencies: ["AudioTeeCore"],
      path: "Sources/AudioTeeCLI"
    ),

    .executableTarget(
      name: "MeetingCaptureCLI",
      dependencies: ["AudioTeeCore"],
      path: "Sources/MeetingCaptureCLI"
    ),

    .executableTarget(
      name: "MeetingCaptureSelfTest",
      dependencies: ["AudioTeeCore"],
      path: "Tests/MeetingCaptureSelfTest"
    ),

    // Tests for the library
    .testTarget(
      name: "AudioTeeCoreTests",
      dependencies: ["AudioTeeCore"],
      path: "Tests/AudioTeeCoreTests"
    ),
  ]
)
