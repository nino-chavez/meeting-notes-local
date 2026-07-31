import AudioToolbox
import CoreAudio
import Foundation

public class AudioRecorder {
  private var deviceID: AudioObjectID
  private var ioProcID: AudioDeviceIOProcID?
  private var finalFormat: AudioStreamBasicDescription!
  private var audioBuffer: AudioBuffer?
  private var outputHandler: AudioOutputHandler
  private var converter: AudioFormatConverter?
  private let strictConversion: Bool
  private let sourceBytesPerFrame: Int
  private var expectedNextSampleTime: Float64?

  /// The audio format this recorder produces (after any conversion).
  public var outputFormat: AudioStreamBasicDescription {
    return finalFormat
  }

  /// Whether this recorder is performing sample rate conversion.
  public var isConverting: Bool {
    return converter != nil
  }

  public init(
    deviceID: AudioObjectID, outputHandler: AudioOutputHandler, convertToSampleRate: Double? = nil,
    chunkDuration: Double = 0.2,
    strictConversion: Bool = false
  ) throws {
    self.deviceID = deviceID
    self.outputHandler = outputHandler
    self.strictConversion = strictConversion

    // Get source format and set up conversion if requested
    let sourceFormat = try AudioFormatManager.getDeviceFormat(deviceID: deviceID)
    self.sourceBytesPerFrame = max(Int(sourceFormat.mBytesPerFrame), 1)

    // Set up the audio buffer using source format and configurable chunk duration
    self.audioBuffer = AudioBuffer(format: sourceFormat, chunkDuration: chunkDuration)

    if let targetSampleRate = convertToSampleRate {
      // Validate sample rate
      guard AudioFormatConverter.isValidSampleRate(targetSampleRate) else {
        AudioTeeLogging.logger.error(
          "Invalid sample rate", context: ["sample_rate": String(targetSampleRate)])
        if strictConversion { throw AudioConverterError.invalidFormat }
        self.converter = nil
        self.finalFormat = sourceFormat
        return
      }

      do {
        let converter = try AudioFormatConverter.toSampleRate(targetSampleRate, from: sourceFormat)
        self.converter = converter
        self.finalFormat = converter.targetFormatDescription
        AudioTeeLogging.logger.info(
          "Audio conversion enabled", context: ["target_sample_rate": String(targetSampleRate)])
      } catch {
        if strictConversion { throw error }
        AudioTeeLogging.logger.error(
          "Failed to create audio converter, using original format",
          context: ["error": String(describing: error)])
        self.converter = nil
        self.finalFormat = sourceFormat
      }
    } else {
      self.converter = nil
      self.finalFormat = sourceFormat
    }
  }

  public func startRecording() throws {
    AudioTeeLogging.logger.debug("Starting audio recording")

    // Log format info and send metadata for final format
    AudioFormatManager.logFormatInfo(finalFormat)
    let metadata = AudioFormatManager.createMetadata(for: finalFormat)
    outputHandler.handleMetadata(metadata)
    outputHandler.handleStreamStart()

    try setupAndStartIOProc()

    AudioTeeLogging.logger.info("Audio device started successfully")
  }

  // Note to self, what about installTap? Would require audio engine and a node?
  // No; AudioEngine.installTap() can only fire as often as 100ms. too slow for us
  private func setupAndStartIOProc() throws {
    AudioTeeLogging.logger.debug("Creating IO proc")
    var status = AudioDeviceCreateIOProcID(
      deviceID,
      {
        (inDevice, inNow, inInputData, inInputTime, outOutputData, inOutputTime, inClientData)
          -> OSStatus in
        let recorder = Unmanaged<AudioRecorder>.fromOpaque(inClientData!).takeUnretainedValue()
        return recorder.processAudio(inInputData, timestamp: inInputTime)
      },
      Unmanaged.passUnretained(self).toOpaque(),
      &ioProcID
    )

    guard status == noErr else {
      throw AudioTeeError.ioProcCreationFailed(status)
    }

    AudioTeeLogging.logger.debug("Starting audio device")
    status = AudioDeviceStart(deviceID, ioProcID)

    if status != noErr {
      cleanupIOProc()
      throw AudioTeeError.deviceStartFailed(status)
    }
  }

  private func processAudio(
    _ inputData: UnsafePointer<AudioBufferList>,
    timestamp: UnsafePointer<AudioTimeStamp>
  ) -> OSStatus {
    let bufferList = inputData.pointee
    let firstBuffer = bufferList.mBuffers

    guard let sourcePointer = firstBuffer.mData, firstBuffer.mDataByteSize > 0 else {
      AudioTeeLogging.logger.error("Received empty audio buffer")
      return noErr
    }

    // Copy directly from the Core Audio buffer into our ring buffer.
    // This avoids creating an intermediate Data object (heap alloc + memcpy)
    // on every IO callback (~10ms). The pointer is valid for the duration
    // of this callback, so this is safe.
    let bytes = Int(firstBuffer.mDataByteSize)
    // kAudioTimeStampSampleTimeValid is bit zero. The SDK imports the field as
    // UInt32 but does not consistently expose the C enum case to Swift.
    if timestamp.pointee.mFlags.rawValue & 1 != 0 {
      let actual = timestamp.pointee.mSampleTime
      if let expectedNextSampleTime, abs(actual - expectedNextSampleTime) > 0.5 {
        outputHandler.handleFailure(.timelineDiscontinuity)
      }
      expectedNextSampleTime = actual + Float64(bytes / sourceBytesPerFrame)
    }

    guard audioBuffer?.append(from: sourcePointer, count: bytes) == true else {
      outputHandler.handleFailure(.bufferOverflow)
      return noErr
    }

    processAudioBuffer()

    return noErr
  }

  public func stopRecording() {
    // Stop callbacks before touching the single-threaded converter and ring
    // buffer from the caller's shutdown thread.
    cleanupIOProc()
    processAudioBuffer()
    audioBuffer?.drainRemainder { pointer, count in
      self.processChunk(pointer, count: count)
    }
    outputHandler.handleStreamStop()
  }

  private func processAudioBuffer() {
    audioBuffer?.processChunks { pointer, count in
      self.processChunk(pointer, count: count)
    }
  }

  private func processChunk(_ pointer: UnsafeRawPointer, count: Int) {
    if let converter {
      if !converter.transform(
        from: pointer, count: count,
        handler: { outPtr, outCount in
          self.outputHandler.handleAudioData(outPtr, count: outCount)
        })
      {
        outputHandler.handleFailure(.conversionFailed)
        if !strictConversion {
          outputHandler.handleAudioData(pointer, count: count)
        }
      }
    } else {
      outputHandler.handleAudioData(pointer, count: count)
    }
  }

  private func cleanupIOProc() {
    if let ioProcID = ioProcID {
      AudioDeviceStop(deviceID, ioProcID)
      AudioDeviceDestroyIOProcID(deviceID, ioProcID)
      self.ioProcID = nil
    }
  }
}
