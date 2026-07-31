import AudioTeeCore
import CoreAudio
import Darwin
import Foundation

private struct SelfTestFailure: Error, CustomStringConvertible {
  let description: String
}

private func require(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
  if try !condition() { throw SelfTestFailure(description: message) }
}

private final class FakeSource: MeetingAudioSource, @unchecked Sendable {
  let leg: MeetingCaptureLeg
  let started = DispatchSemaphore(value: 0)
  var stopTail: Data?
  private let lock = NSLock()
  private var pcm: (@Sendable (Data) -> Void)?
  private var failure: (@Sendable (MeetingCaptureFault) -> Void)?
  private(set) var stops = 0

  init(_ leg: MeetingCaptureLeg) { self.leg = leg }

  func start(
    onPCM: @escaping @Sendable (Data) -> Void,
    onFailure: @escaping @Sendable (MeetingCaptureFault) -> Void
  ) throws {
    lock.lock()
    pcm = onPCM
    failure = onFailure
    lock.unlock()
    started.signal()
  }

  func stop() {
    lock.lock()
    stops += 1
    let tail = stopTail
    let callback = pcm
    lock.unlock()
    if let tail { callback?(tail) }
  }

  func emit(_ data: Data) {
    lock.lock()
    let callback = pcm
    lock.unlock()
    callback?(data)
  }
}

private final class UpdateBox: @unchecked Sendable {
  let recording = DispatchSemaphore(value: 0)
  let terminal = DispatchSemaphore(value: 0)
  private let lock = NSLock()
  private(set) var updates: [MeetingCaptureUpdate] = []

  func receive(_ update: MeetingCaptureUpdate) {
    lock.lock()
    updates.append(update)
    lock.unlock()
    if update == .recording { recording.signal() }
    if update != .recording { terminal.signal() }
  }
}

private struct Fixture {
  let url: URL
  let directoryFD: Int32

  init() throws {
    url = FileManager.default.temporaryDirectory.appendingPathComponent(
      "meeting-capture-self-test-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(
      at: url, withIntermediateDirectories: false,
      attributes: [.posixPermissions: 0o700])
    guard chmod(url.path, mode_t(0o700)) == 0 else {
      throw SelfTestFailure(description: "cannot set fixture mode")
    }
    directoryFD = open(url.path, O_RDONLY | O_CLOEXEC)
    guard directoryFD >= 0 else {
      throw SelfTestFailure(description: "cannot open fixture directory")
    }
  }

  func close() {
    Darwin.close(directoryFD)
    try? FileManager.default.removeItem(at: url)
  }

  func names() throws -> [String] {
    try FileManager.default.contentsOfDirectory(atPath: url.path).sorted()
  }

  func assertWAV(_ name: String, frames: Int) throws {
    let path = url.appendingPathComponent(name)
    let data = try Data(contentsOf: path)
    try require(data.count == 44 + frames * 2, "\(name) byte count is wrong")
    try require(String(data: data[0..<4], encoding: .ascii) == "RIFF", "\(name) lacks RIFF")
    try require(String(data: data[8..<12], encoding: .ascii) == "WAVE", "\(name) lacks WAVE")
    try require(readUInt32(data, at: 24) == 16_000, "\(name) sample rate is wrong")
    try require(readUInt32(data, at: 40) == UInt32(frames * 2), "\(name) frame count is wrong")
    try require(data[20] == 1 && data[22] == 1 && data[34] == 16, "\(name) PCM format is wrong")
    var metadata = stat()
    try require(lstat(path.path, &metadata) == 0, "\(name) metadata is unreadable")
    try require(metadata.st_mode & 0o777 == 0o600, "\(name) mode is not 0600")
  }

  func assertPCM(_ name: String, equals expected: Data) throws {
    let data = try Data(contentsOf: url.appendingPathComponent(name))
    try require(Data(data.dropFirst(44)) == expected, "\(name) PCM payload is wrong")
  }

  private func readUInt32(_ data: Data, at offset: Int) -> UInt32 {
    UInt32(data[offset])
      | UInt32(data[offset + 1]) << 8
      | UInt32(data[offset + 2]) << 16
      | UInt32(data[offset + 3]) << 24
  }
}

private func wait(_ semaphore: DispatchSemaphore, _ message: String) throws {
  try require(semaphore.wait(timeout: .now() + 2) == .success, message)
}

private func testOrderedFinalization() throws {
  let fixture = try Fixture()
  defer { fixture.close() }
  let mic = FakeSource(.mic)
  let system = FakeSource(.system)
  let updates = UpdateBox()
  let coordinator = try MeetingCaptureCoordinator(
    directoryFD: fixture.directoryFD, mic: mic, system: system,
    onUpdate: { update in updates.receive(update) })

  try require(try fixture.names().isEmpty, "files exist before activation")
  coordinator.activate()
  try wait(mic.started, "mic did not start")
  try wait(system.started, "system did not start")
  try require(try fixture.names().isEmpty, "activation opened files before readiness")
  mic.emit(Data([1, 0]))
  try require(try fixture.names().isEmpty, "one ready leg opened files")
  system.emit(Data([2, 0]))
  try wait(updates.recording, "both ready legs did not enter recording")
  try require(
    try fixture.names() == [".mic.wav.partial", ".system.wav.partial"],
    "recording did not create exactly two partial WAVs")

  mic.emit(Data([0x11, 0, 0x12, 0, 0x13, 0]))
  system.emit(Data([0x21, 0, 0x22, 0]))
  system.stopTail = Data([0x23, 0, 0x24, 0])
  let receipt = coordinator.stop()
  try wait(updates.terminal, "stop did not produce a terminal event")
  try require(
    receipt == MeetingCaptureReceipt(micSamples: 3, systemSamples: 4),
    "stop did not preserve the source's synchronous tail frames")
  system.emit(Data([0x25, 0]))
  try require(try fixture.names() == ["mic.wav", "system.wav"], "stop did not promote pair")
  try fixture.assertWAV("mic.wav", frames: 3)
  try fixture.assertWAV("system.wav", frames: 4)
  try fixture.assertPCM(
    "system.wav", equals: Data([0x21, 0, 0x22, 0, 0x23, 0, 0x24, 0]))
}

private func testNoOverwrite() throws {
  let fixture = try Fixture()
  defer { fixture.close() }
  let marker = Data("keep".utf8)
  let existing = fixture.url.appendingPathComponent("mic.wav")
  try marker.write(to: existing)
  _ = chmod(existing.path, mode_t(0o600))

  let mic = FakeSource(.mic)
  let system = FakeSource(.system)
  let updates = UpdateBox()
  let coordinator = try MeetingCaptureCoordinator(
    directoryFD: fixture.directoryFD, mic: mic, system: system,
    onUpdate: { update in updates.receive(update) })
  coordinator.activate()
  try wait(mic.started, "mic did not start")
  try wait(system.started, "system did not start")
  mic.emit(Data([1, 0]))
  system.emit(Data([1, 0]))
  try wait(updates.terminal, "no-overwrite did not fail")
  try require(try Data(contentsOf: existing) == marker, "existing mic.wav changed")
  try require(try fixture.names() == ["mic.wav"], "no-overwrite left new files")
}

private func testLateSecondLegCollisionRollsBackFirstPromotion() throws {
  let fixture = try Fixture()
  defer { fixture.close() }
  let mic = FakeSource(.mic)
  let system = FakeSource(.system)
  let updates = UpdateBox()
  let coordinator = try MeetingCaptureCoordinator(
    directoryFD: fixture.directoryFD, mic: mic, system: system,
    onUpdate: { update in updates.receive(update) })
  coordinator.activate()
  try wait(mic.started, "mic did not start")
  try wait(system.started, "system did not start")
  mic.emit(Data([1, 0]))
  system.emit(Data([1, 0]))
  try wait(updates.recording, "late-collision fixture did not record")
  mic.emit(Data([0x31, 0]))
  system.emit(Data([0x41, 0]))

  let marker = Data("existing-system-marker".utf8)
  let systemFinal = fixture.url.appendingPathComponent("system.wav")
  try marker.write(to: systemFinal)
  _ = chmod(systemFinal.path, mode_t(0o600))

  try require(coordinator.stop() == nil, "late collision returned a final receipt")
  try wait(updates.terminal, "late collision did not produce a terminal event")
  try require(try Data(contentsOf: systemFinal) == marker, "existing system marker changed")
  try require(
    try fixture.names() == [".mic.wav.partial", ".system.wav.partial", "system.wav"],
    "late collision left a newly-final mic leg")
  try fixture.assertWAV(".mic.wav.partial", frames: 1)
  try fixture.assertWAV(".system.wav.partial", frames: 1)
}

private func testOverflowAndInterrupt() throws {
  do {
    let fixture = try Fixture()
    defer { fixture.close() }
    let mic = FakeSource(.mic)
    let system = FakeSource(.system)
    let updates = UpdateBox()
    let coordinator = try MeetingCaptureCoordinator(
      directoryFD: fixture.directoryFD, mic: mic, system: system,
      maxPendingBytes: 4, onUpdate: { update in updates.receive(update) })
    coordinator.activate()
    try wait(mic.started, "mic did not start")
    try wait(system.started, "system did not start")
    mic.emit(Data([1, 0]))
    system.emit(Data([1, 0]))
    try wait(updates.recording, "overflow fixture did not record")
    mic.emit(Data([1, 0, 2, 0, 3, 0]))
    try wait(updates.terminal, "bounded overflow was not terminal")
    try require(
      !FileManager.default.fileExists(atPath: fixture.url.appendingPathComponent("mic.wav").path),
      "overflow promoted mic.wav")
    try fixture.assertWAV(".mic.wav.partial", frames: 0)
    try fixture.assertWAV(".system.wav.partial", frames: 0)
  }

  do {
    let fixture = try Fixture()
    defer { fixture.close() }
    let mic = FakeSource(.mic)
    let system = FakeSource(.system)
    let updates = UpdateBox()
    let coordinator = try MeetingCaptureCoordinator(
      directoryFD: fixture.directoryFD, mic: mic, system: system,
      onUpdate: { update in updates.receive(update) })
    coordinator.activate()
    try wait(mic.started, "mic did not start")
    try wait(system.started, "system did not start")
    mic.emit(Data([1, 0]))
    system.emit(Data([1, 0]))
    try wait(updates.recording, "interrupt fixture did not record")
    mic.emit(Data([1, 0, 2, 0]))
    system.emit(Data([3, 0]))
    coordinator.interrupt()
    try wait(updates.terminal, "interrupt was not terminal")
    try require(
      try fixture.names() == [".mic.wav.partial", ".system.wav.partial"],
      "interrupt promoted capture files")
    try fixture.assertWAV(".mic.wav.partial", frames: 2)
    try fixture.assertWAV(".system.wav.partial", frames: 1)
  }
}

private func testCoreBufferOverflowAndTailDrain() throws {
  let format = AudioStreamBasicDescription(
    mSampleRate: 16_000,
    mFormatID: kAudioFormatLinearPCM,
    mFormatFlags: kAudioFormatFlagIsPacked | kAudioFormatFlagIsSignedInteger,
    mBytesPerPacket: 2,
    mFramesPerPacket: 1,
    mBytesPerFrame: 2,
    mChannelsPerFrame: 1,
    mBitsPerChannel: 16,
    mReserved: 0)
  let full = AudioTeeCore.AudioBuffer(format: format, chunkDuration: 0.2)
  let capacity = Data(repeating: 1, count: 16_000 * 2 * 10)
  let accepted = capacity.withUnsafeBytes { bytes in
    full.append(from: bytes.baseAddress!, count: bytes.count)
  }
  try require(accepted, "core capture buffer refused its declared capacity")
  let overflow = Data([2, 2]).withUnsafeBytes { bytes in
    full.append(from: bytes.baseAddress!, count: bytes.count)
  }
  try require(!overflow, "core capture buffer overflow was silent")

  let tail = AudioTeeCore.AudioBuffer(format: format, chunkDuration: 0.2)
  let expected = Data(repeating: 0x7A, count: 318)
  _ = expected.withUnsafeBytes { bytes in
    tail.append(from: bytes.baseAddress!, count: bytes.count)
  }
  var drained: Data?
  tail.drainRemainder { pointer, count in
    drained = Data(bytes: pointer, count: count)
  }
  try require(drained == expected, "core capture buffer dropped its final partial chunk")
}

do {
  try testOrderedFinalization()
  try testNoOverwrite()
  try testLateSecondLegCollisionRollsBackFirstPromotion()
  try testOverflowAndInterrupt()
  try testCoreBufferOverflowAndTailDrain()
  print("meeting-capture self-test: pass")
  exit(0)
} catch {
  FileHandle.standardError.write(Data("meeting-capture self-test: FAIL: \(error)\n".utf8))
  exit(1)
}
