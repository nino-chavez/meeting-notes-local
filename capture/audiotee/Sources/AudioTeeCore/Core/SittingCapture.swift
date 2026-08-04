import Darwin
import Foundation

public struct SittingCaptureReceipt: Codable, Equatable, Sendable {
  public let micSamples: Int

  public init(micSamples: Int) {
    self.micSamples = micSamples
  }
}

public enum SittingCaptureUpdate: Equatable, Sendable {
  case recording
  case finalized(SittingCaptureReceipt)
  case failed(MeetingCaptureFault)
  case interrupted
}

/// Streams one microphone leg to an inherited pipe for a voice-profile sitting.
///
/// This deliberately owns no files. Sitting evidence is admitted by the
/// application's evidence store, which accumulates the raw audio and its digest
/// through its own write path; a helper that wrote `audio.raw` itself would put
/// a second writer inside the store's boundary. So the audio descriptor must be
/// a pipe — a regular file is refused at construction — and the helper's whole
/// output is a byte stream plus events.
///
/// End-of-stream is NOT completion authority. This process closes the pipe on
/// every terminal path, including interruption, so the parent must treat EOF as
/// "no more bytes" and admit the sitting only after the `finalized` event whose
/// sample count matches the bytes it drained. A parent that trusts EOF alone
/// admits a truncated take.
///
/// Mirrors `MeetingCaptureCoordinator`'s discipline: the first valid block
/// establishes readiness and is discarded, the stream writer opens only after
/// readiness, blocks are whole signed 16-bit samples, and the bounded writer
/// refuses rather than buffering without limit when the parent stops draining.
public final class SittingCaptureCoordinator: @unchecked Sendable {
  private let mic: MeetingAudioSource
  private let audioFD: Int32
  private let maxPendingBytes: Int
  private let onUpdate: @Sendable (SittingCaptureUpdate) -> Void
  private let controlQueue = DispatchQueue(label: "local-meeting-notes.sitting-control")
  private let lock = NSLock()

  private var _state: MeetingCaptureState = .paused
  private var stopDraining = false
  private var storedFault: MeetingCaptureFault?
  private var writer: BoundedPipeWriter?

  public init(
    audioFD: Int32,
    mic: MeetingAudioSource,
    maxPendingBytes: Int = 16_000 * 2 * 5,
    onUpdate: @escaping @Sendable (SittingCaptureUpdate) -> Void
  ) throws {
    guard mic.leg == .mic else {
      throw MeetingCaptureFault(
        code: "source_leg_mismatch", detail: "sitting capture records the microphone leg only")
    }
    guard maxPendingBytes > 0 else {
      throw MeetingCaptureFault(
        code: "invalid_queue_limit", detail: "sitting stream limit must be positive")
    }
    guard fcntl(audioFD, F_GETFD) != -1 else {
      throw MeetingCaptureFault(
        code: "sitting_stream_unavailable", detail: "sitting audio descriptor is invalid")
    }
    var metadata = stat()
    guard fstat(audioFD, &metadata) == 0, (metadata.st_mode & S_IFMT) == S_IFIFO else {
      throw MeetingCaptureFault(
        code: "sitting_stream_unavailable",
        detail: "sitting audio descriptor must be a pipe, never a file this helper owns")
    }

    self.audioFD = audioFD
    self.mic = mic
    self.maxPendingBytes = maxPendingBytes
    self.onUpdate = onUpdate
  }

  public var state: MeetingCaptureState {
    lock.withLock { _state }
  }

  public func activate() {
    controlQueue.async { [self] in
      guard transition(from: .paused, to: .arming) else {
        fail(
          MeetingCaptureFault(
            code: "invalid_start", detail: "sitting start is valid only while paused"))
        return
      }
      do {
        try mic.start(
          onPCM: { [weak self] data in self?.receive(data) },
          onFailure: { [weak self] fault in self?.recordSource(fault) })
      } catch let fault as MeetingCaptureFault {
        fail(fault)
      } catch {
        fail(
          MeetingCaptureFault(
            code: "source_start_failed", detail: String(describing: error)))
      }
    }
  }

  @discardableResult
  public func stop() -> SittingCaptureReceipt? {
    controlQueue.sync { finish(promote: true, interrupted: false) }
  }

  public func interrupt() {
    controlQueue.sync {
      _ = finish(promote: false, interrupted: true)
    }
  }

  public func abort(_ fault: MeetingCaptureFault) {
    controlQueue.sync {
      _ = finish(promote: false, interrupted: false, failure: fault)
    }
  }

  private func receive(_ data: Data) {
    guard !data.isEmpty else { return }
    let snapshot = lock.withLock { (_state, writer, stopDraining) }
    switch snapshot.0 {
    case .arming:
      controlQueue.async { [weak self] in self?.markReady() }
    case .recording:
      append(data, to: snapshot.1)
    case .stopping where snapshot.2:
      append(data, to: snapshot.1)
    case .paused, .stopping, .terminal:
      break
    }
  }

  private func append(_ data: Data, to writer: BoundedPipeWriter?) {
    guard data.count.isMultiple(of: 2), let writer else {
      record(
        MeetingCaptureFault(
          code: "invalid_pcm", leg: .mic,
          detail: "normalized PCM must contain whole signed 16-bit samples"))
      return
    }
    if !writer.append(data) {
      record(
        MeetingCaptureFault(
          code: "sitting_stream_overflow", leg: .mic,
          detail: "bounded sitting stream refused audio; the parent stopped draining"))
    }
  }

  private func record(_ fault: MeetingCaptureFault) {
    let shouldSchedule = lock.withLock { () -> Bool in
      guard _state != .terminal else { return false }
      if storedFault == nil { storedFault = fault }
      return _state != .stopping
    }
    if shouldSchedule {
      controlQueue.async { [weak self] in self?.fail(fault) }
    }
  }

  private func recordSource(_ fault: MeetingCaptureFault) {
    let accepted = lock.withLock { _state != .stopping || stopDraining }
    if accepted { record(fault) }
  }

  private func markReady() {
    guard state == .arming else { return }
    do {
      let newWriter = try BoundedPipeWriter(
        audioFD: audioFD, maxPendingBytes: maxPendingBytes,
        onFailure: { [weak self] fault in self?.record(fault) })
      lock.withLock {
        writer = newWriter
        _state = .recording
      }
      onUpdate(.recording)
    } catch let fault as MeetingCaptureFault {
      fail(fault)
    } catch {
      fail(
        MeetingCaptureFault(
          code: "sitting_stream_unavailable", detail: String(describing: error)))
    }
  }

  private func fail(_ fault: MeetingCaptureFault) {
    guard state != .terminal else { return }
    _ = finish(promote: false, interrupted: false, failure: fault)
  }

  private func finish(
    promote: Bool,
    interrupted: Bool,
    failure: MeetingCaptureFault? = nil
  ) -> SittingCaptureReceipt? {
    let prior = state
    guard prior != .terminal else { return nil }
    lock.withLock {
      _state = .stopping
      if writer != nil { stopDraining = true }
    }

    mic.stop()
    lock.withLock { stopDraining = false }

    let activeWriter = lock.withLock { writer }
    var receipt: SittingCaptureReceipt?
    var terminalFault = failure ?? lock.withLock { storedFault }
    if let activeWriter {
      let samples = activeWriter.finish()
      if terminalFault == nil, activeWriter.fault != nil {
        terminalFault = activeWriter.fault
      }
      receipt = SittingCaptureReceipt(micSamples: samples)
    }

    lock.withLock {
      writer = nil
      _state = .terminal
    }

    if interrupted {
      onUpdate(.interrupted)
    } else if let terminalFault {
      onUpdate(.failed(terminalFault))
    } else if let receipt, promote {
      onUpdate(.finalized(receipt))
    } else {
      onUpdate(
        .failed(
          MeetingCaptureFault(
            code: "capture_not_ready", detail: "sitting stopped before the microphone was ready")))
    }
    return terminalFault == nil && promote && !interrupted ? receipt : nil
  }

  private func transition(from: MeetingCaptureState, to: MeetingCaptureState) -> Bool {
    lock.withLock {
      guard _state == from else { return false }
      _state = to
      return true
    }
  }
}

/// One serial writer over the inherited pipe with a bounded pending budget.
///
/// The bound exists because the reader is the application's storage authority:
/// if it stops draining, buffering here would hide that failure until memory
/// pressure made it somebody else's. Refusal surfaces it immediately as a
/// capture fault instead.
private final class BoundedPipeWriter: @unchecked Sendable {
  private let descriptor: Int32
  private let maxPendingBytes: Int
  private let onFailure: @Sendable (MeetingCaptureFault) -> Void
  private let queue = DispatchQueue(label: "local-meeting-notes.sitting-stream")
  private let lock = NSLock()

  private var pendingBytes = 0
  private var frames = 0
  private var storedFault: MeetingCaptureFault?
  private var closing = false
  private var closed = false

  init(
    audioFD: Int32,
    maxPendingBytes: Int,
    onFailure: @escaping @Sendable (MeetingCaptureFault) -> Void
  ) throws {
    let retained = dup(audioFD)
    guard retained >= 0 else {
      throw MeetingCaptureFault(
        code: "sitting_stream_unavailable", detail: "cannot retain sitting audio descriptor")
    }
    self.descriptor = retained
    self.maxPendingBytes = maxPendingBytes
    self.onFailure = onFailure
  }

  deinit {
    if !closed { close(descriptor) }
  }

  var fault: MeetingCaptureFault? { lock.withLock { storedFault } }

  func append(_ data: Data) -> Bool {
    guard !data.isEmpty, data.count.isMultiple(of: 2) else { return false }
    let accepted = lock.withLock { () -> Bool in
      guard !closing, storedFault == nil else { return false }
      guard pendingBytes + data.count <= maxPendingBytes else {
        storedFault = MeetingCaptureFault(
          code: "sitting_stream_overflow", leg: .mic,
          detail: "bounded sitting stream exceeded \(maxPendingBytes) bytes")
        return false
      }
      pendingBytes += data.count
      return true
    }
    guard accepted else { return false }

    queue.async { [self] in
      var failure: MeetingCaptureFault?
      data.withUnsafeBytes { (bytes: UnsafeRawBufferPointer) in
        guard let base = bytes.baseAddress else { return }
        var written = 0
        while written < bytes.count {
          let result = Darwin.write(descriptor, base.advanced(by: written), bytes.count - written)
          if result > 0 {
            written += result
          } else if result < 0, errno == EINTR {
            continue
          } else {
            failure = MeetingCaptureFault(
              code: "sitting_stream_write_failed", leg: .mic,
              detail: "sitting stream write failed with errno \(errno)")
            return
          }
        }
      }
      let report = lock.withLock { () -> MeetingCaptureFault? in
        pendingBytes -= data.count
        if let failure, storedFault == nil {
          storedFault = failure
          return failure
        }
        if failure == nil { frames += data.count / 2 }
        return nil
      }
      if let report { onFailure(report) }
    }
    return true
  }

  /// Drains the serial queue, half-closes the pipe so the reader sees EOF, and
  /// returns the exact frames written. Idempotence is not needed: the
  /// coordinator's terminal transition calls this once.
  func finish() -> Int {
    lock.withLock { closing = true }
    queue.sync {}
    return lock.withLock { () -> Int in
      if !closed {
        close(descriptor)
        closed = true
      }
      return frames
    }
  }
}
