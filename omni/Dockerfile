# tkt as a container image: make build.docker fills the context with an assimilated executable per arch, since docker execs an entrypoint without the shell an ape needs.
ARG BASE=debian:bookworm-slim

FROM ${BASE} AS tkt
ARG TARGETARCH
COPY ${TARGETARCH}/ /usr/local/bin/
WORKDIR /work
ENTRYPOINT ["tkt"]
