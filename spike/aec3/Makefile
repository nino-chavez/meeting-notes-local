# AEC3 needs webrtc-audio-processing built and on PKG_CONFIG_PATH. It is not
# vendored here and there is no Homebrew formula, so the path is explicit rather
# than discovered — a build that silently found a different version would put a
# different canceller in the measurement.
#
#   git clone --depth 1 https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing.git
#   cd webrtc-audio-processing
#   meson setup build -Dprefix=$PWD/../wap-install --buildtype=release
#   ninja -C build install
#   export PKG_CONFIG_PATH=$PWD/../wap-install/lib/pkgconfig
#
# The prefix must NOT be inside the source tree on macOS: the repo ships a file
# called INSTALL, and a case-insensitive filesystem makes `install/` collide with
# it, which surfaces as a bare NotADirectoryError from meson.

PKG := webrtc-audio-processing-2
CXX ?= c++
# -Wno-nullability-completeness: clang on macOS emits this for every raw pointer in
# the WebRTC public headers — 17 warnings from a dependency we do not patch, which
# is enough noise to hide a real one from this file. Scoped to that check only, so
# -Wall -Wextra still applies to our own code.
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -Wno-nullability-completeness

CHECK := $(shell pkg-config --exists $(PKG) && echo yes)
ifneq ($(CHECK),yes)
$(error $(PKG) not found by pkg-config. Set PKG_CONFIG_PATH to the lib/pkgconfig \
of a webrtc-audio-processing install — see the comment at the top of this Makefile)
endif

PKG_CFLAGS := $(shell pkg-config --cflags $(PKG))
PKG_LIBS := $(shell pkg-config --libs $(PKG))
LIBDIR := $(shell pkg-config --variable=libdir $(PKG))

all: aec3_offline

# -rpath so the binary finds the dylib without DYLD_LIBRARY_PATH in every shell
# that runs it. A tool that only works under one exported variable gets run
# without it eventually, and dyld's failure is louder than the wrong answer but
# still a waste of a take.
aec3_offline: aec3_offline.cpp
	$(CXX) $(CXXFLAGS) $(PKG_CFLAGS) -o $@ $< $(PKG_LIBS) -Wl,-rpath,$(LIBDIR)

clean:
	rm -f aec3_offline

.PHONY: all clean
