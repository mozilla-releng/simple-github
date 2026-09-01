FROM debian:13@sha256:f324c7ff54321e8d9c588493a20244965938ce0aa50bbd1022d38010e9ffc4b1

### Add worker user and setup its workspace.
RUN mkdir /builds && \
    groupadd -g 1000 worker && \
    useradd -u 1000 -g 1000 -d /builds/worker -s /bin/bash -m worker && \
    mkdir -p /builds/worker/workspace && \
    chown -R worker:worker /builds

# Declare default working folder
WORKDIR /builds/worker

RUN apt-get update && \
    apt-get install -y \
      gnupg \
      bzip2 \
      git \
      openssh-client \
      python3-requests \
      python3-zstd \
      unzip

# %include-run-task
