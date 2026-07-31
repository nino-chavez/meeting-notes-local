// Does macOS cancel another application's speaker output on the microphone?
//
// The spike's teardown says "neither OS gives you echo cancellation", sourced to
// a vendor selling echo cancellation and flagged self-serving in the same
// sentence. macOS has shipped a voice-processing path since 10.15
// (AVAudioIONode.setVoiceProcessingEnabled, kAudioUnitSubType_VoiceProcessingIO),
// and Apple documents it for macOS. What Apple does NOT document on those pages
// is the question the product turns on: the reference signal. A canceller can
// only remove what it has a copy of, and every use Apple demonstrates is a voice
// app cancelling *its own* playback. In a meeting the far end is rendered by Zoom
// — a different process, a different audio unit.
//
// If the platform canceller references the output DEVICE, it removes Zoom's audio
// and the product needs no canceller of its own. If it references only what the
// enabling process renders, it removes nothing here and WebRTC AEC3 with the tap
// as reference is the only path. Days of build work hang on which, and no amount
// of reading settles it, because the docs do not say.
//
// So: record the microphone twice over the same playback, once treated and once
// not, and compare. Say nothing during either take — the far end is the whole
// signal, so its level IS the echo, and a human in the room would only add noise
// to the one measurement that does not need one.
//
// Usage: aec-probe --out FILE --seconds N [--voice-processing]

import AVFoundation
import Foundation

let RATE = 16000.0  // what the rest of the pipeline reads

func fail(_ message: String) -> Never {
  FileHandle.standardError.write(Data("\(message)\n".utf8))
  exit(1)
}

struct Options {
  var out = "mic.wav"
  var seconds = 12.0
  var voiceProcessing = false
  var diagnose = false
  var channel = 0
  var play: String?
}

func parse() -> Options {
  var o = Options()
  var it = CommandLine.arguments.dropFirst().makeIterator()
  while let a = it.next() {
    switch a {
    case "--out": o.out = it.next() ?? o.out
    case "--seconds": o.seconds = Double(it.next() ?? "") ?? o.seconds
    case "--voice-processing": o.voiceProcessing = true
    case "--diagnose": o.diagnose = true
    case "--channel": o.channel = Int(it.next() ?? "") ?? o.channel
    case "--play": o.play = it.next()
    case "-h", "--help":
      print("""
        aec-probe --out FILE --seconds N [--voice-processing]
                  [--channel N] [--diagnose]

        Records the default input to a 16 kHz mono WAV. With --voice-processing,
        asks macOS for its voice-processing path first and reports what it
        actually got — the request can be refused, and a refused request that
        recorded anyway would read as "the canceller did nothing".

        Enabling voice processing changes the input format: this machine goes
        from 1 channel to 9. --diagnose records nothing and prints the level of
        each input channel instead, which is how you find out which one carries
        the processed microphone rather than guessing and measuring silence.
        --channel picks the one to write (default 0).

        --play FILE renders a WAV through THIS engine's own output while
        recording. That is the positive control for a negative result: if voice
        processing cancels audio it rendered itself but not audio another process
        rendered, the canceller works and simply cannot see other processes —
        which is a fact about the architecture. Without this control, "no
        cancellation" is indistinguishable from "the probe was misconfigured".
        """)
      exit(0)
    default:
      fail("unknown argument \(a)")
    }
  }
  return o
}

let opts = parse()
let engine = AVAudioEngine()
let input = engine.inputNode

// Ask first, then read back. Never report the request as the state: a throw here
// or a silent refusal would otherwise be recorded as a treated take that showed
// no suppression, which is the same file as "the canceller does not work" and
// would send the whole decision the wrong way.
if opts.voiceProcessing {
  do {
    try input.setVoiceProcessingEnabled(true)
  } catch {
    fail("voice processing refused: \(error.localizedDescription)")
  }
}
let got = input.isVoiceProcessingEnabled
if opts.voiceProcessing && !got {
  fail("asked for voice processing and the node reports it off — refusing to "
       + "write a take that would read as treated")
}

let inFormat = input.outputFormat(forBus: 0)
guard inFormat.sampleRate > 0, inFormat.channelCount > 0 else {
  fail("no input format — the microphone is unavailable, most likely a "
       + "microphone permission this terminal has not been granted")
}

// --diagnose: measure each input channel instead of writing a file. The point is
// to locate the processed microphone in a format whose layout is undocumented,
// before any comparison is drawn from a channel that might hold nothing.
if opts.diagnose {
  let channels = Int(inFormat.channelCount)
  var sums = [Double](repeating: 0, count: channels)
  var count = 0
  let dlock = NSLock()
  input.installTap(onBus: 0, bufferSize: 4096, format: inFormat) { buf, _ in
    guard let data = buf.floatChannelData else { return }
    let n = Int(buf.frameLength)
    var local = [Double](repeating: 0, count: channels)
    for c in 0..<channels {
      var acc = 0.0
      for i in 0..<n { let v = Double(data[c][i]); acc += v * v }
      local[c] = acc
    }
    dlock.lock()
    for c in 0..<channels { sums[c] += local[c] }
    count += n
    dlock.unlock()
  }
  do { try engine.start() } catch { fail("engine will not start: \(error)") }
  print("measuring \(channels) input channels for \(opts.seconds)s — "
    + "voice processing \(got ? "ON" : "off")")
  Thread.sleep(forTimeInterval: opts.seconds)
  input.removeTap(onBus: 0)
  engine.stop()
  dlock.lock(); let total = count; let acc = sums; dlock.unlock()
  guard total > 0 else { fail("no input frames arrived") }
  for c in 0..<channels {
    let rms = (acc[c] / Double(total)).squareRoot()
    let db = 20 * log10(rms + 1e-12)
    print(String(format: "  channel %d  rms %.6f  %+7.1f dBFS%@", c, rms, db,
                 rms < 1e-9 ? "   (digital silence)" : ""))
  }
  exit(0)
}

let url = URL(fileURLWithPath: opts.out)
let settings: [String: Any] = [
  AVFormatIDKey: kAudioFormatLinearPCM,
  AVSampleRateKey: RATE,
  AVNumberOfChannelsKey: 1,
  AVLinearPCMBitDepthKey: 16,
  AVLinearPCMIsFloatKey: false,
  AVLinearPCMIsBigEndianKey: false,
  AVLinearPCMIsNonInterleaved: false,
]
// Optional, and released explicitly below. AVAudioFile fixes up the WAV header's
// data-chunk length when it deallocates, and nothing else does: held to process
// exit, it leaves a file full of audio that every reader sees as zero frames.
var file: AVAudioFile?
do {
  file = try AVAudioFile(forWriting: url, settings: settings)
} catch {
  fail("cannot write \(opts.out): \(error)")
}
let writeFormat = file!.processingFormat
guard let converter = AVAudioConverter(from: inFormat, to: writeFormat) else {
  fail("no converter from \(inFormat) to 16 kHz mono")
}
// Many-to-one needs an explicit map. Left to itself the converter produced
// digital silence from the 9-channel voice-processing format — a file whose RMS
// is exactly zero, which next to an untreated take reads as perfect cancellation
// rather than as a broken channel mapping. There is no mixdown that would be
// right here anyway: the extra channels are not more microphone.
if inFormat.channelCount > writeFormat.channelCount {
  guard opts.channel < Int(inFormat.channelCount) else {
    fail("--channel \(opts.channel) but the input has \(inFormat.channelCount)")
  }
  converter.channelMap = [NSNumber(value: opts.channel)]
}

// Written from the tap thread and read by the main thread at the end, so the
// count that goes on stdout is the count that reached the file.
let lock = NSLock()
var written: AVAudioFramePosition = 0
var writeError: Error?

input.installTap(onBus: 0, bufferSize: 4096, format: inFormat) { buf, _ in
  let ratio = RATE / inFormat.sampleRate
  let capacity = AVAudioFrameCount(Double(buf.frameLength) * ratio) + 1024
  guard let out = AVAudioPCMBuffer(pcmFormat: writeFormat,
                                   frameCapacity: capacity) else { return }
  var supplied = false
  var err: NSError?
  // The converter pulls: hand it this buffer once, then say "nothing right now"
  // so it returns what it has and stays open for the next callback. Handing the
  // same buffer twice is how a resampler silently duplicates audio — and saying
  // `.endOfStream` instead is how it silently stops: the first version of this
  // did, which closes the stream permanently, so every later callback returned
  // immediately and a ten-second take wrote 0.10 seconds.
  let status = converter.convert(to: out, error: &err) { _, outStatus in
    if supplied {
      outStatus.pointee = .noDataNow
      return nil
    }
    supplied = true
    outStatus.pointee = .haveData
    return buf
  }
  guard status != .error, out.frameLength > 0 else { return }
  lock.lock()
  defer { lock.unlock() }
  guard writeError == nil, let sink = file else { return }
  do {
    try sink.write(from: out)
    written += AVAudioFramePosition(out.frameLength)
  } catch {
    writeError = error
  }
}

// Attached before the engine starts, and connected through the main mixer so the
// render path is the ordinary one a voice app would use.
var player: AVAudioPlayerNode?
if let path = opts.play {
  guard let src = try? AVAudioFile(forReading: URL(fileURLWithPath: path)) else {
    fail("cannot read \(path) to play")
  }
  let node = AVAudioPlayerNode()
  engine.attach(node)
  engine.connect(node, to: engine.mainMixerNode, format: src.processingFormat)
  node.scheduleFile(src, at: nil)
  player = node
}

do {
  try engine.start()
} catch {
  fail("engine will not start: \(error)")
}
player?.play()

print("recording \(opts.seconds)s at \(Int(RATE)) Hz mono — "
  + "voice processing \(got ? "ON" : "off"), input \(Int(inFormat.sampleRate)) Hz "
  + "\(inFormat.channelCount)ch"
  + (opts.play.map { ", rendering \($0) through this engine" } ?? ""))
Thread.sleep(forTimeInterval: opts.seconds)
player?.stop()
input.removeTap(onBus: 0)
engine.stop()
// removeTap first: the closure holds a reference, so nilling this while the tap
// is installed would not release the file and would not finalize the header.
lock.lock()
file = nil
lock.unlock()

lock.lock()
let frames = written
let failure = writeError
lock.unlock()
if let failure {
  fail("write failed: \(failure)")
}
// A short file is a failure, not a result. The converter bug above wrote 0.10s of
// a 10s take and said so only because the frame count was printed; compared
// against another take of the same length it would have looked like a quiet room.
let seconds = Double(frames) / RATE
if seconds < opts.seconds * 0.9 {
  fail(String(format: "wrote only %.2fs of a %.1fs take — refusing to leave a "
              + "truncated file that would read as a quiet one", seconds, opts.seconds))
}
// Read it back rather than trusting the write. The header bug above produced a
// 318 KB file that every reader reported as empty, and a probe whose output is
// compared against another take cannot afford to be wrong about that quietly.
guard let readback = try? AVAudioFile(forReading: url) else {
  fail("wrote \(opts.out) and cannot reopen it")
}
if readback.length != frames {
  fail("wrote \(frames) frames but \(opts.out) reads back as \(readback.length)")
}
print("wrote \(opts.out) — \(frames) frames, "
  + String(format: "%.2fs", seconds) + ", verified readable")
