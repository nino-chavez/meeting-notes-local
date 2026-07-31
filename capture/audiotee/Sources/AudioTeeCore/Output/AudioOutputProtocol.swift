import Foundation

/// Protocol for handling audio output in different formats
public protocol AudioOutputHandler {
  /// Called with a pointer to raw PCM audio data. The pointer is only
  /// valid for the duration of this call.
  func handleAudioData(_ pointer: UnsafeRawPointer, count: Int)
  func handleMetadata(_ metadata: AudioStreamMetadata)
  func handleStreamStart()
  func handleStreamStop()
  func handleFailure(_ failure: AudioOutputFailure)
}

public enum AudioOutputFailure: Error, Equatable, Sendable {
  case bufferOverflow
  case conversionFailed
  case timelineDiscontinuity
}

extension AudioOutputHandler {
  public func handleFailure(_ failure: AudioOutputFailure) {}
}
