// Real AEC3 over a recorded pair of legs, so it can be scored on the same table
// as the offline estimate in aec_bound.py.
//
// Shape follows the vendor's own examples/run-offline.cpp from
// webrtc-audio-processing: feed the far end to ProcessReverseStream, the
// microphone to ProcessStream, block by block, in capture order. That ordering is
// the contract — AEC3 estimates the echo path from the reference it has already
// seen, so handing it the whole far end up front, or the near end first, measures
// something else.
//
// Two deliberate departures from that example.
//
// It reads and writes WAV at 16 kHz rather than headerless PCM at 48 kHz, because
// that is what this project records and what the gate embeds. AEC3 runs natively
// at 16 kHz, so nothing is resampled and no resampler artefact lands in the
// comparison.
//
// And the gain controllers are OFF by default, where the example turns them on.
// This output gets compared against `raw`, `linear` and `masked` conditions whose
// levels are otherwise untouched; an adaptive gain would move the level of every
// admitted window and show up as recovery that the echo canceller did not do.
// --agc and --ns turn them on for the operating matrix, where the question is
// what the product should ship rather than how much echo was removed.

// The vendor example includes modules/audio_processing/include/audio_processing.h,
// which in 2.1 is a header whose own comment calls it transitional and which
// forwards here. Included at its real location so a future release retiring the
// forward is a no-op rather than a break.
#include <api/audio/audio_processing.h>

#include <algorithm>
#include <cmath>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

namespace {

constexpr int kRate = 16000;
constexpr int kChannels = 1;
constexpr int kBlockMs = 10;  // AEC3's native block; not a tunable
constexpr size_t kBlock = kRate * kBlockMs / 1000;

// A minimal RIFF reader that refuses anything it was not given. Guessing at a
// format here would put resampled or half-speed audio into a measurement and
// nothing downstream would notice: every file in this project is 16 kHz mono
// 16-bit by construction, so anything else is a mistake upstream, not an input to
// accommodate.
bool ReadWav(const std::string& path, std::vector<int16_t>* out, std::string* err) {
  std::ifstream f(path, std::ios::binary);
  if (!f) { *err = "cannot open " + path; return false; }

  char riff[12];
  f.read(riff, 12);
  if (f.gcount() != 12 || std::memcmp(riff, "RIFF", 4) || std::memcmp(riff + 8, "WAVE", 4)) {
    *err = path + " is not a RIFF/WAVE file";
    return false;
  }

  bool have_fmt = false;
  while (f) {
    char id[4];
    uint32_t size = 0;
    f.read(id, 4);
    f.read(reinterpret_cast<char*>(&size), 4);
    if (f.gcount() != 4) break;

    if (!std::memcmp(id, "fmt ", 4)) {
      std::vector<char> fmt(size);
      f.read(fmt.data(), size);
      if (size < 16) { *err = path + ": truncated fmt chunk"; return false; }
      uint16_t format, channels, bits;
      uint32_t rate;
      std::memcpy(&format, fmt.data() + 0, 2);
      std::memcpy(&channels, fmt.data() + 2, 2);
      std::memcpy(&rate, fmt.data() + 4, 4);
      std::memcpy(&bits, fmt.data() + 14, 2);
      if (format != 1 || channels != kChannels || rate != kRate || bits != 16) {
        char buf[256];
        std::snprintf(buf, sizeof(buf),
                      "%s is format %u, %u ch, %u Hz, %u-bit — this reads only "
                      "16-bit PCM mono at %d Hz",
                      path.c_str(), format, channels, rate, bits, kRate);
        *err = buf;
        return false;
      }
      have_fmt = true;
    } else if (!std::memcmp(id, "data", 4)) {
      if (!have_fmt) { *err = path + ": data chunk before fmt chunk"; return false; }
      out->resize(size / sizeof(int16_t));
      f.read(reinterpret_cast<char*>(out->data()), size);
      if (static_cast<uint32_t>(f.gcount()) != size) {
        *err = path + ": data chunk shorter than its header claims";
        return false;
      }
      return true;
    } else {
      f.seekg(size + (size & 1), std::ios::cur);  // chunks are word-aligned
    }
  }
  *err = path + ": no data chunk";
  return false;
}

bool WriteWav(const std::string& path, const std::vector<int16_t>& x, std::string* err) {
  std::ofstream f(path, std::ios::binary);
  if (!f) { *err = "cannot write " + path; return false; }
  const uint32_t bytes = static_cast<uint32_t>(x.size() * sizeof(int16_t));
  const uint32_t rate = kRate;
  const uint16_t channels = kChannels, bits = 16, format = 1;
  const uint32_t byte_rate = rate * channels * bits / 8;
  const uint16_t align = channels * bits / 8;
  const uint32_t riff_size = 36 + bytes, fmt_size = 16;

  f.write("RIFF", 4);
  f.write(reinterpret_cast<const char*>(&riff_size), 4);
  f.write("WAVEfmt ", 8);
  f.write(reinterpret_cast<const char*>(&fmt_size), 4);
  f.write(reinterpret_cast<const char*>(&format), 2);
  f.write(reinterpret_cast<const char*>(&channels), 2);
  f.write(reinterpret_cast<const char*>(&rate), 4);
  f.write(reinterpret_cast<const char*>(&byte_rate), 4);
  f.write(reinterpret_cast<const char*>(&align), 2);
  f.write(reinterpret_cast<const char*>(&bits), 2);
  f.write("data", 4);
  f.write(reinterpret_cast<const char*>(&bytes), 4);
  f.write(reinterpret_cast<const char*>(x.data()), bytes);
  if (!f) { *err = "write of " + path + " failed"; return false; }
  return true;
}

double Rms(const int16_t* x, size_t n) {
  double acc = 0;
  for (size_t i = 0; i < n; ++i) {
    const double v = x[i] / 32768.0;
    acc += v * v;
  }
  return n ? std::sqrt(acc / n) : 0.0;
}

void Usage(const char* argv0) {
  std::fprintf(stderr,
    "usage: %s --mic FILE --ref FILE --out FILE [--agc] [--ns] [--delay-ms N]\n"
    "\n"
    "  --mic    the microphone leg, 16 kHz mono 16-bit WAV\n"
    "  --ref    the system leg over the same interval, same format\n"
    "  --out    where to write the cancelled microphone\n"
    "  --agc    enable the gain controllers. Off by default: this output is\n"
    "           compared against conditions whose levels are untouched, and an\n"
    "           adaptive gain reads as recovery the canceller did not do\n"
    "  --ns     enable noise suppression, same reasoning\n"
    "  --delay-ms  hint the initial echo path delay. AEC3 estimates this itself;\n"
    "           the two legs here start within about 7 ms, so 0 is honest\n",
    argv0);
}

}  // namespace

int main(int argc, char** argv) {
  std::string mic_path, ref_path, out_path;
  bool agc = false, ns = false;
  int delay_ms = 0;

  for (int i = 1; i < argc; ++i) {
    const std::string a = argv[i];
    auto next = [&](const char* what) -> std::string {
      if (i + 1 >= argc) { std::fprintf(stderr, "%s needs a value\n", what); std::exit(2); }
      return argv[++i];
    };
    if (a == "--mic") mic_path = next("--mic");
    else if (a == "--ref") ref_path = next("--ref");
    else if (a == "--out") out_path = next("--out");
    else if (a == "--agc") agc = true;
    else if (a == "--ns") ns = true;
    else if (a == "--delay-ms") delay_ms = std::stoi(next("--delay-ms"));
    else if (a == "-h" || a == "--help") { Usage(argv[0]); return 0; }
    else { std::fprintf(stderr, "unknown argument %s\n", a.c_str()); return 2; }
  }
  if (mic_path.empty() || ref_path.empty() || out_path.empty()) {
    Usage(argv[0]);
    return 2;
  }

  std::vector<int16_t> mic, ref;
  std::string err;
  if (!ReadWav(mic_path, &mic, &err) || !ReadWav(ref_path, &ref, &err)) {
    std::fprintf(stderr, "%s\n", err.c_str());
    return 1;
  }

  // The legs run on independent clocks and legitimately differ — measured at a
  // few thousand samples over two minutes. Processing stops at the shorter one
  // rather than feeding AEC3 silence it would adapt to as a genuine echo path.
  const size_t blocks = std::min(mic.size(), ref.size()) / kBlock;
  if (blocks == 0) {
    std::fprintf(stderr,
                 "nothing to process: %zu mic and %zu reference samples, and a "
                 "block is %zu\n", mic.size(), ref.size(), kBlock);
    return 1;
  }

  rtc::scoped_refptr<webrtc::AudioProcessing> apm =
      webrtc::AudioProcessingBuilder().Create();
  if (!apm) {
    std::fprintf(stderr, "AudioProcessingBuilder returned nothing\n");
    return 1;
  }
  webrtc::AudioProcessing::Config config;
  config.echo_canceller.enabled = true;
  config.echo_canceller.mobile_mode = false;  // AEC3, not AECM
  config.high_pass_filter.enabled = true;     // AEC3 expects it; not a gain change
  if (agc) {
    config.gain_controller1.enabled = true;
    config.gain_controller1.mode =
        webrtc::AudioProcessing::Config::GainController1::kAdaptiveDigital;
    config.gain_controller2.enabled = true;
  }
  if (ns) {
    config.noise_suppression.enabled = true;
  }
  apm->ApplyConfig(config);

  const webrtc::StreamConfig stream_config(kRate, kChannels);
  std::vector<int16_t> out(blocks * kBlock);
  std::vector<int16_t> ref_block(kBlock);

  for (size_t b = 0; b < blocks; ++b) {
    const size_t off = b * kBlock;
    // The reference goes in first and is copied, because ProcessReverseStream
    // writes through its output pointer: passing the source array would mutate
    // the reference leg in place and every later block would see processed audio
    // where the recording should be.
    std::memcpy(ref_block.data(), ref.data() + off, kBlock * sizeof(int16_t));
    if (apm->ProcessReverseStream(ref_block.data(), stream_config, stream_config,
                                  ref_block.data()) != 0) {
      std::fprintf(stderr, "ProcessReverseStream failed at block %zu\n", b);
      return 1;
    }
    if (delay_ms > 0) apm->set_stream_delay_ms(delay_ms);
    if (apm->ProcessStream(mic.data() + off, stream_config, stream_config,
                           out.data() + off) != 0) {
      std::fprintf(stderr, "ProcessStream failed at block %zu\n", b);
      return 1;
    }
  }

  if (!WriteWav(out_path, out, &err)) {
    std::fprintf(stderr, "%s\n", err.c_str());
    return 1;
  }

  // Printed so a run that cancelled nothing says so here rather than looking like
  // a scoring result later. This is a whole-file level change, not suppression:
  // the operator's own voice is in both numbers, so a real echo-only figure comes
  // from aec_bound.py over the protocol's silent intervals.
  const double before = Rms(mic.data(), blocks * kBlock);
  const double after = Rms(out.data(), out.size());
  std::printf("%zu blocks (%.2fs)  mic %.1f dBFS -> %.1f dBFS  "
              "whole-file change %+.1f dB  [echo canceller%s%s]\n",
              blocks, blocks * kBlockMs / 1000.0,
              20 * std::log10(before + 1e-12), 20 * std::log10(after + 1e-12),
              20 * std::log10((after + 1e-12) / (before + 1e-12)),
              agc ? ", agc" : "", ns ? ", noise suppression" : "");
  return 0;
}
