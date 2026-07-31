import Darwin
import Foundation
import XCTest

@testable import AudioTeeCore

private final class FakeMeetingAudioSource: MeetingAudioSource, @unchecked Sendable {
  let leg: MeetingCaptureLeg
  var onStart: (() -> Void)?
  private let lock = NSLock()
  private var pcm: (@Sendable (Data) -> Void)?
  private var failure: (@Sendable (MeetingCaptureFault) -> Void)?
  private(set) var stopCount = 0

  init(leg: MeetingCaptureLeg) { self.leg = leg }

  func start(
    onPCM: @escaping @Sendable (Data) -> Void,
    onFailure: @escaping @Sendable (MeetingCaptureFault) -> Void
  ) throws {
    lock.lock()
    pcm = onPCM
    failure = onFailure
    lock.unlock()
    onStart?()
  }

  func stop() {
    lock.lock()
    stopCount += 1
    lock.unlock()
  }

  func emit(_ data: Data) {
    lock.lock()
    let callback = pcm
    lock.unlock()
    callback?(data)
  }

  func fail(_ fault: MeetingCaptureFault) {
    lock.lock()
    let callback = failure
    lock.unlock()
    callback?(fault)
  }
}

final class MeetingCaptureTests: XCTestCase {
  private var temporary: URL!
  private var directoryFD: Int32 = -1

  override func setUpWithError() throws {
    temporary = FileManager.default.temporaryDirectory.appendingPathComponent(
      "meeting-capture-tests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(
      at: temporary, withIntermediateDirectories: false,
      attributes: [.posixPermissions: 0o700])
    XCTAssertEqual(chmod(temporary.path, mode_t(0o700)), 0)
    directoryFD = open(temporary.path, O_RDONLY | O_CLOEXEC)
    XCTAssertGreaterThanOrEqual(directoryFD, 0)
  }

  override func tearDownWithError() throws {
    if directoryFD >= 0 { close(directoryFD) }
    try? FileManager.default.removeItem(at: temporary)
  }

  func testBothLegsMustBeReadyBeforePrivateWAVsOpenAndStopPromotesExactFrames() throws {
    let mic = FakeMeetingAudioSource(leg: .mic)
    let system = FakeMeetingAudioSource(leg: .system)
    let started = expectation(description: "both sources started")
    started.expectedFulfillmentCount = 2
    mic.onStart = { started.fulfill() }
    system.onStart = { started.fulfill() }
    let recording = expectation(description: "recording")
    let finalized = expectation(description: "finalized")
    let updates = LockedUpdates()
    let coordinator = try MeetingCaptureCoordinator(
      directoryFD: directoryFD, mic: mic, system: system
    ) { update in
      updates.append(update)
      if update == .recording { recording.fulfill() }
      if case .finalized = update { finalized.fulfill() }
    }

    XCTAssertEqual(try contents(), [])
    XCTAssertEqual(coordinator.state, .paused)
    coordinator.activate()
    wait(for: [started], timeout: 2)
    XCTAssertEqual(try contents(), [])

    // Readiness blocks are deliberately discarded, and one leg is insufficient.
    mic.emit(Data([0x01, 0x00]))
    XCTAssertEqual(try contents(), [])
    system.emit(Data([0x02, 0x00]))
    wait(for: [recording], timeout: 2)
    XCTAssertEqual(
      try contents(), [".mic.wav.partial", ".system.wav.partial"])
    try assertMode(".mic.wav.partial", 0o600)
    try assertMode(".system.wav.partial", 0o600)

    mic.emit(Data([0x11, 0x00, 0x12, 0x00, 0x13, 0x00]))
    system.emit(Data([0x21, 0x00, 0x22, 0x00]))
    let receipt = coordinator.stop()
    wait(for: [finalized], timeout: 2)

    XCTAssertEqual(receipt, MeetingCaptureReceipt(micSamples: 3, systemSamples: 2))
    XCTAssertEqual(try contents(), ["mic.wav", "system.wav"])
    try assertWAV("mic.wav", frames: 3)
    try assertWAV("system.wav", frames: 2)
    try assertMode("mic.wav", 0o600)
    try assertMode("system.wav", 0o600)
    XCTAssertEqual(mic.stopCount, 1)
    XCTAssertEqual(system.stopCount, 1)
    XCTAssertEqual(updates.values.last, .finalized(receipt!))
  }

  func testExistingFinalArtifactFailsBeforeAnyPartialIsCreated() throws {
    let marker = Data("keep".utf8)
    try marker.write(to: temporary.appendingPathComponent("mic.wav"))
    XCTAssertEqual(chmod(temporary.appendingPathComponent("mic.wav").path, 0o600), 0)

    let mic = FakeMeetingAudioSource(leg: .mic)
    let system = FakeMeetingAudioSource(leg: .system)
    let failed = expectation(description: "no overwrite failure")
    let coordinator = try MeetingCaptureCoordinator(
      directoryFD: directoryFD, mic: mic, system: system
    ) { update in
      if case .failed(let fault) = update, fault.code == "capture_no_overwrite" {
        failed.fulfill()
      }
    }
    activateAndWait(coordinator, mic: mic, system: system)
    mic.emit(Data([1, 0]))
    system.emit(Data([1, 0]))
    wait(for: [failed], timeout: 2)

    XCTAssertEqual(try Data(contentsOf: temporary.appendingPathComponent("mic.wav")), marker)
    XCTAssertEqual(try contents(), ["mic.wav"])
    XCTAssertEqual(coordinator.state, .terminal)
  }

  func testBoundedQueueOverflowIsExplicitAndNeverPromotes() throws {
    let mic = FakeMeetingAudioSource(leg: .mic)
    let system = FakeMeetingAudioSource(leg: .system)
    let recording = expectation(description: "recording")
    let failed = expectation(description: "overflow")
    let coordinator = try MeetingCaptureCoordinator(
      directoryFD: directoryFD, mic: mic, system: system, maxPendingBytes: 4
    ) { update in
      if update == .recording { recording.fulfill() }
      if case .failed(let fault) = update, fault.code == "writer_queue_overflow" {
        failed.fulfill()
      }
    }
    activateAndWait(coordinator, mic: mic, system: system)
    mic.emit(Data([1, 0]))
    system.emit(Data([1, 0]))
    wait(for: [recording], timeout: 2)

    mic.emit(Data([1, 0, 2, 0, 3, 0]))
    wait(for: [failed], timeout: 2)
    XCTAssertEqual(coordinator.state, .terminal)
    XCTAssertFalse(
      FileManager.default.fileExists(atPath: temporary.appendingPathComponent("mic.wav").path))
    XCTAssertFalse(
      FileManager.default.fileExists(atPath: temporary.appendingPathComponent("system.wav").path))
    try assertWAV(".mic.wav.partial", frames: 0)
    try assertWAV(".system.wav.partial", frames: 0)
  }

  func testInterruptedCaptureClosesReadablePartialsWithoutPromotion() throws {
    let mic = FakeMeetingAudioSource(leg: .mic)
    let system = FakeMeetingAudioSource(leg: .system)
    let recording = expectation(description: "recording")
    let interrupted = expectation(description: "interrupted")
    let coordinator = try MeetingCaptureCoordinator(
      directoryFD: directoryFD, mic: mic, system: system
    ) { update in
      if update == .recording { recording.fulfill() }
      if update == .interrupted { interrupted.fulfill() }
    }
    activateAndWait(coordinator, mic: mic, system: system)
    mic.emit(Data([1, 0]))
    system.emit(Data([1, 0]))
    wait(for: [recording], timeout: 2)
    mic.emit(Data([1, 0, 2, 0]))
    system.emit(Data([3, 0]))

    coordinator.interrupt()
    wait(for: [interrupted], timeout: 2)
    XCTAssertEqual(try contents(), [".mic.wav.partial", ".system.wav.partial"])
    try assertWAV(".mic.wav.partial", frames: 2)
    try assertWAV(".system.wav.partial", frames: 1)
    XCTAssertEqual(coordinator.state, .terminal)
  }

  private func activateAndWait(
    _ coordinator: MeetingCaptureCoordinator,
    mic: FakeMeetingAudioSource,
    system: FakeMeetingAudioSource
  ) {
    let started = expectation(description: "sources started")
    started.expectedFulfillmentCount = 2
    mic.onStart = { started.fulfill() }
    system.onStart = { started.fulfill() }
    coordinator.activate()
    wait(for: [started], timeout: 2)
  }

  private func contents() throws -> [String] {
    try FileManager.default.contentsOfDirectory(atPath: temporary.path).sorted()
  }

  private func assertMode(_ name: String, _ expected: mode_t) throws {
    var metadata = stat()
    XCTAssertEqual(lstat(temporary.appendingPathComponent(name).path, &metadata), 0)
    XCTAssertEqual(metadata.st_mode & 0o777, expected)
  }

  private func assertWAV(_ name: String, frames: Int) throws {
    let data = try Data(contentsOf: temporary.appendingPathComponent(name))
    XCTAssertEqual(data.count, 44 + frames * 2)
    XCTAssertEqual(String(data: data[0..<4], encoding: .ascii), "RIFF")
    XCTAssertEqual(String(data: data[8..<12], encoding: .ascii), "WAVE")
    XCTAssertEqual(readUInt32(data, at: 24), 16_000)
    XCTAssertEqual(readUInt32(data, at: 40), UInt32(frames * 2))
    XCTAssertEqual(data[20], 1)
    XCTAssertEqual(data[22], 1)
    XCTAssertEqual(data[34], 16)
  }

  private func readUInt32(_ data: Data, at offset: Int) -> UInt32 {
    UInt32(data[offset])
      | UInt32(data[offset + 1]) << 8
      | UInt32(data[offset + 2]) << 16
      | UInt32(data[offset + 3]) << 24
  }
}

private final class LockedUpdates: @unchecked Sendable {
  private let lock = NSLock()
  private var storage: [MeetingCaptureUpdate] = []

  var values: [MeetingCaptureUpdate] {
    lock.lock()
    defer { lock.unlock() }
    return storage
  }

  func append(_ update: MeetingCaptureUpdate) {
    lock.lock()
    storage.append(update)
    lock.unlock()
  }
}
