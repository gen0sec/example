# Two images from one file: `token` provisions a SoftHSM token, `synapse` is the
# Synapse image with the SoftHSM module added. A real HSM needs neither: you
# install your vendor's PKCS#11 module instead.
ARG SYNAPSE_IMAGE=registry.gen0sec.com/gen0sec/synapse:0.8.9

FROM debian:13 AS token
RUN apt-get update \
 && apt-get install -y --no-install-recommends softhsm2 opensc openssl \
 && rm -rf /var/lib/apt/lists/*
ENV SOFTHSM2_CONF=/etc/synapse/softhsm2.conf

FROM debian:13 AS softhsm
RUN apt-get update \
 && apt-get install -y --no-install-recommends softhsm2 \
 && rm -rf /var/lib/apt/lists/*

# The Synapse image has no shell and no package manager, so the module is
# copied in. Its libraries (libcrypto, libstdc++, libz, libzstd) are already there.
FROM ${SYNAPSE_IMAGE} AS synapse
COPY --from=softhsm /usr/lib/softhsm/libsofthsm2.so /usr/lib/softhsm/libsofthsm2.so
ENV SOFTHSM2_CONF=/etc/synapse/softhsm2.conf
