# MinIO no longer publishes official container images, so the server and the
# mc client are built here from the official upstream source at pinned tags.

FROM golang:1.24-alpine AS build

ARG MINIO_TAG=RELEASE.2025-10-15T17-29-55Z
ARG MINIO_COMMIT=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
ARG MINIO_VERSION=2025-10-15T17:29:55Z
ARG MC_TAG=RELEASE.2025-08-13T08-35-41Z
ARG MC_VERSION=2025-08-13T08:35:41Z

ENV CGO_ENABLED=0 GOTOOLCHAIN=local

RUN apk add --no-cache git

WORKDIR /src/minio
RUN git clone --depth 1 --branch "${MINIO_TAG}" https://github.com/minio/minio.git . \
    && test "$(git rev-parse HEAD)" = "${MINIO_COMMIT}" \
    && go build -tags kqueue -trimpath \
        -ldflags "$(MINIO_RELEASE=RELEASE go run buildscripts/gen-ldflags.go "${MINIO_VERSION}")" \
        -o /out/minio .

WORKDIR /src/mc
RUN git clone --depth 1 --branch "${MC_TAG}" https://github.com/minio/mc.git . \
    && go build -tags kqueue -trimpath \
        -ldflags "$(MC_RELEASE=RELEASE go run buildscripts/gen-ldflags.go "${MC_VERSION}")" \
        -o /out/mc .

FROM alpine:3.22

RUN apk add --no-cache ca-certificates curl

COPY --from=build /out/minio /out/mc /usr/local/bin/

VOLUME /data
EXPOSE 9000 9001

ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
