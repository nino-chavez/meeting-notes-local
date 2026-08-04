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


private final class SittingUpdateBox: @unchecked Sendable {
  let recording = DispatchSemaphore(value: 0)
  let terminal = DispatchSemaphore(value: 0)
  private let lock = NSLock()
  private(set) var updates: [SittingCaptureUpdate] = []

  func receive(_ update: SittingCaptureUpdate) {
    lock.lock()
    updates.append(update)
    lock.unlock()
    if update == .recording { recording.signal() }
    if update != .recording { terminal.signal() }
  }
}

private final class SittingReceiptBox: @unchecked Sendable {
  private let lock = NSLock()
  private var stored: SittingCaptureReceipt?

  var value: SittingCaptureReceipt? {
    lock.lock()
    defer { lock.unlock() }
    return stored
  }

  func store(_ receipt: SittingCaptureReceipt?) {
    lock.lock()
    stored = receipt
    lock.unlock()
  }
}

private final class PipeReader: @unchecked Sendable {
  private let lock = NSLock()
  private var collected = Data()
  private let finished = DispatchSemaphore(value: 0)

  init(descriptor: Int32) {
    Thread.detachNewThread { [self] in
      var chunk = [UInt8](repeating: 0, count: 4096)
      while true {
        let count = read(descriptor, &chunk, chunk.count)
        if count > 0 {
          lock.lock()
          collected.append(contentsOf: chunk[0..<count])
          lock.unlock()
        } else if count < 0, errno == EINTR {
          continue
        } else {
          break
        }
      }
      close(descriptor)
      finished.signal()
    }
  }

  func drained() throws -> Data {
    try require(finished.wait(timeout: .now() + 2) == .success, "sitting stream never closed")
    lock.lock()
    defer { lock.unlock() }
    return collected
  }
}

private func testSittingStreamsExactBytesAndRefusesFiles() throws {
  // A regular file must be refused: the evidence store is the only writer of
  // durable sitting bytes, so the helper only ever holds a pipe.
  let filePath = FileManager.default.temporaryDirectory
    .appendingPathComponent("sitting-self-test-\(UUID().uuidString)")
  FileManager.default.createFile(atPath: filePath.path, contents: Data())
  defer { try? FileManager.default.removeItem(at: filePath) }
  let fileFD = open(filePath.path, O_WRONLY)
  try require(fileFD >= 0, "cannot open sitting file fixture")
  defer { close(fileFD) }
  do {
    _ = try SittingCaptureCoordinator(
      audioFD: fileFD, mic: FakeSource(.mic), onUpdate: { _ in })
    try require(false, "sitting coordinator accepted a regular file")
  } catch let fault as MeetingCaptureFault {
    try require(
      fault.code == "sitting_stream_unavailable", "file refusal used the wrong code")
  }

  var descriptors: [Int32] = [0, 0]
  try require(pipe(&descriptors) == 0, "cannot create sitting pipe")
  let mic = FakeSource(.mic)
  let updates = SittingUpdateBox()
  let coordinator = try SittingCaptureCoordinator(
    audioFD: descriptors[1], mic: mic, onUpdate: { update in updates.receive(update) })
  let reader = PipeReader(descriptor: descriptors[0])

  do {
    _ = try SittingCaptureCoordinator(
      audioFD: descriptors[1], mic: FakeSource(.system), onUpdate: { _ in })
    try require(false, "sitting coordinator accepted a non-microphone source")
  } catch let fault as MeetingCaptureFault {
    try require(fault.code == "source_leg_mismatch", "leg refusal used the wrong code")
  }
  coordinator.activate()
  try wait(mic.started, "sitting mic did not start")
  mic.emit(Data([9, 9]))  // readiness block: establishes recording, never streamed
  try wait(updates.recording, "sitting readiness did not enter recording")
  close(descriptors[1])  // the writer holds its own retained descriptor now

  mic.emit(Data([0x11, 0, 0x12, 0, 0x13, 0]))
  mic.stopTail = Data([0x14, 0, 0x15, 0])
  let receipt = coordinator.stop()
  try wait(updates.terminal, "sitting stop did not produce a terminal event")
  try require(
    receipt == SittingCaptureReceipt(micSamples: 5),
    "sitting stop did not preserve the synchronous tail frames")
  try require(
    try reader.drained() == Data([0x11, 0, 0x12, 0, 0x13, 0, 0x14, 0, 0x15, 0]),
    "sitting stream bytes do not match the emitted PCM exactly")
}

private func testSittingOverflowAndInterrupt() throws {
  do {
    var descriptors: [Int32] = [0, 0]
    try require(pipe(&descriptors) == 0, "cannot create overflow pipe")
    let mic = FakeSource(.mic)
    let updates = SittingUpdateBox()
    let coordinator = try SittingCaptureCoordinator(
      audioFD: descriptors[1], mic: mic, maxPendingBytes: 4,
      onUpdate: { update in updates.receive(update) })
    let reader = PipeReader(descriptor: descriptors[0])
    coordinator.activate()
    try wait(mic.started, "overflow sitting mic did not start")
    mic.emit(Data([9, 9]))
    try wait(updates.recording, "overflow sitting did not record")
    close(descriptors[1])
    mic.emit(Data([1, 0, 2, 0, 3, 0]))
    try wait(updates.terminal, "sitting overflow was not terminal")
    var sawOverflow = false
    if case .failed(let fault) = updates.updates.last, fault.code == "sitting_stream_overflow" {
      sawOverflow = true
    }
    try require(sawOverflow, "sitting overflow did not fail with its own code")
    _ = try reader.drained()
  }

  do {
    var descriptors: [Int32] = [0, 0]
    try require(pipe(&descriptors) == 0, "cannot create interrupt pipe")
    let mic = FakeSource(.mic)
    let updates = SittingUpdateBox()
    let coordinator = try SittingCaptureCoordinator(
      audioFD: descriptors[1], mic: mic, onUpdate: { update in updates.receive(update) })
    let reader = PipeReader(descriptor: descriptors[0])
    coordinator.activate()
    try wait(mic.started, "interrupt sitting mic did not start")
    mic.emit(Data([9, 9]))
    try wait(updates.recording, "interrupt sitting did not record")
    close(descriptors[1])
    mic.emit(Data([1, 0, 2, 0]))
    coordinator.interrupt()
    try wait(updates.terminal, "sitting interrupt was not terminal")
    try require(
      updates.updates.last == .interrupted, "sitting interrupt emitted the wrong terminal")
    // Bytes may have been streamed before the interruption; the parent's
    // finalized-event join is what refuses them, and EOF must still arrive.
    _ = try reader.drained()
  }
}


private func testSittingStalledReaderFailsInsteadOfWedging() throws {
  // The reviewed deadlock: a reader that stays alive but stops draining fills
  // the pipe, a blocking write wedges the writer queue, finish() wedges behind
  // it, and every control path hangs with no terminal event. The non-blocking
  // stall deadline must turn that into a terminal failure instead — and stop()
  // must return rather than hang.
  var descriptors: [Int32] = [0, 0]
  try require(pipe(&descriptors) == 0, "cannot create stall pipe")
  let mic = FakeSource(.mic)
  let updates = SittingUpdateBox()
  let coordinator = try SittingCaptureCoordinator(
    audioFD: descriptors[1], mic: mic, maxPendingBytes: 4 << 20,
    writeStallSeconds: 1.0,
    onUpdate: { update in updates.receive(update) })
  coordinator.activate()
  try wait(mic.started, "stall sitting mic did not start")
  mic.emit(Data([9, 9]))
  try wait(updates.recording, "stall sitting did not record")
  close(descriptors[1])

  // Nobody reads descriptors[0]; a macOS pipe absorbs at most 64 KiB, so the
  // second emission is guaranteed to hit EAGAIN and ride the stall deadline.
  mic.emit(Data(repeating: 0, count: 64 << 10))
  mic.emit(Data(repeating: 0, count: 64 << 10))

  // Call stop() while the first block is still riding its 1.0 s stall — this
  // is the exact control path that deadlocked before the non-blocking
  // rewrite: stop → controlQueue.sync → finish → queue.sync parked behind the
  // blocked write, forever, because the stalled reader never drains. The call
  // must come back (without a receipt) once the writer faults; the watchdog
  // semaphore is what turns a regression back into a test failure instead of
  // a hung suite.
  usleep(50_000)  // let the first block enter its write before stopping
  let stopReturned = DispatchSemaphore(value: 0)
  let stopReceipt = SittingReceiptBox()
  Thread.detachNewThread {
    stopReceipt.store(coordinator.stop())
    stopReturned.signal()
  }
  try require(
    stopReturned.wait(timeout: .now() + 4) == .success,
    "stop() during a stalled write did not return; the reviewed deadlock is back")
  try require(stopReceipt.value == nil, "stop during a stalled write returned a receipt")
  try require(
    updates.terminal.wait(timeout: .now() + 4) == .success,
    "stalled reader did not produce a terminal event; the helper would hang")
  var sawStall = false
  if case .failed(let fault) = updates.updates.last, fault.code == "sitting_stream_write_failed" {
    sawStall = true
  }
  try require(sawStall, "stalled reader did not fail with the write-stall code")
  close(descriptors[0])
}

do {
  try testOrderedFinalization()
  try testNoOverwrite()
  try testLateSecondLegCollisionRollsBackFirstPromotion()
  try testOverflowAndInterrupt()
  try testCoreBufferOverflowAndTailDrain()
  try testSittingStreamsExactBytesAndRefusesFiles()
  try testSittingOverflowAndInterrupt()
  try testSittingStalledReaderFailsInsteadOfWedging()
  print("meeting-capture self-test: pass")
  exit(0)
} catch {
  FileHandle.standardError.write(Data("meeting-capture self-test: FAIL: \(error)\n".utf8))
  exit(1)
}
