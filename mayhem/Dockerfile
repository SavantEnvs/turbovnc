# syntax=docker/dockerfile:1.7
# Commit image: the org C/C++ base plus the X server development packages TurboVNC's Xvnc needs, then the
# full repo (with .git) in /mayhem, built by mayhem/build.sh and checked by mayhem/test.sh.
FROM ghcr.io/savantenvs/base:20261023

ARG COMMIT
ARG REPO_URL
ARG SOURCE_DATE_EPOCH
ARG SANITIZER_FLAGS
ARG COVERAGE_FLAGS=
ARG MAYHEM_JOBS=

# Build-time packages for the in-tree Xorg server plus xkbcomp, which Xvnc runs at start-up to compile its
# keymap. They live in the image so mayhem/build.sh and mayhem/test.sh run offline.
USER root
RUN [ -n "$SOURCE_DATE_EPOCH" ] && repro-sources-list.sh || true ; \
    apt-get update && apt-get install -yq --no-install-recommends \
        libx11-dev libxext-dev libxfont-dev libxkbfile-dev libpam0g-dev x11proto-dev xtrans-dev \
        libpixman-1-dev libxau-dev libxdmcp-dev libfontenc-dev libxcb1-dev libgl-dev libdrm-dev \
        libxi-dev libxrandr-dev libxfixes-dev libxt-dev libxcvt-dev libpciaccess-dev xserver-xorg-dev \
        libjpeg-dev libturbojpeg0-dev zlib1g-dev libssl-dev xkb-data x11-xkb-utils \
 && rm -rf /var/lib/apt/lists/*

USER mayhem
WORKDIR /mayhem
COPY --chown=2000:2000 . /mayhem

RUN if [ -x /opt/mayhem/ccache/prefill ]; then /opt/mayhem/ccache/prefill bash mayhem/build.sh; \
    else bash mayhem/build.sh; fi

RUN if [ -f mayhem/test.sh ]; then bash mayhem/test.sh; else echo "no mayhem/test.sh — repo ships no functional tests"; fi

LABEL org.opencontainers.image.source="${REPO_URL}" \
      org.opencontainers.image.revision="${COMMIT}" \
      rlenv.tier="commit" \
      rlenv.source_date_epoch="${SOURCE_DATE_EPOCH}" \
      rlenv.user="mayhem"

USER mayhem
WORKDIR /mayhem
