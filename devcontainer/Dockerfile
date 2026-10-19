FROM ubuntu:26.04

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=${USER_UID}

# Piped RUN steps below must fail on the first failing command, not the last.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo \
    git \
    make \
    ffmpeg \
    curl \
    ca-certificates \
    gnupg \
    openssh-client \
    shellcheck \
    python3-pip \
    python3-venv \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN groupmod --new-name ${USERNAME} "$(getent group ${USER_GID} | cut -d: -f1)" \
    && usermod --login ${USERNAME} --home /home/${USERNAME} --move-home \
       "$(getent passwd ${USER_UID} | cut -d: -f1)" \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

# python3-pip and npm pull in Debian's python3-packaging (via python3-wheel and gyp),
# which pip cannot uninstall (no RECORD file). When a dependency needs a newer one (virtualenv 21.14.11, via pre-commit, needs
# >=26.3), install it alongside in /usr/local, which shadows /usr/lib on sys.path, so the
# main install finds it satisfied instead of trying to replace Debian's copy.
RUN pip3 install --no-cache-dir --break-system-packages --ignore-installed packaging \
    && pip3 install --no-cache-dir --break-system-packages \
    yamllint \
    ansible-lint \
    pre-commit \
    proxmoxer \
    requests \
    google-auth

# actionlint
RUN curl -fsSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash \
    | bash -s -- latest /usr/local/bin

# hadolint
RUN curl -fsSL https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64 \
    -o /usr/local/bin/hadolint && chmod +x /usr/local/bin/hadolint

# gh CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh && rm -rf /var/lib/apt/lists/*

# gcloud CLI
RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && apt-get update && apt-get install -y google-cloud-cli && rm -rf /var/lib/apt/lists/*

# commitlint + Bitwarden CLI. npm as root keeps the owner IDs stored in each tarball, and
# @bitwarden/cli bundles files owned by UIDs above 1.5 billion. Rootless Docker cannot map
# those (only 65536 subordinate IDs) and fails to unpack the layer, so reset ownership in
# this same layer.
RUN npm install -g @commitlint/cli @commitlint/config-conventional @bitwarden/cli \
    && chown -R root:root /usr/local/lib/node_modules

USER ${USERNAME}
