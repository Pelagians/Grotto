if [ -x /home/linuxbrew/.linuxbrew/bin/brew ]; then
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
fi

export PATH="/tools/bin:/tools/npm/bin:/tools/pnpm:/tools/bun/bin:/tools/cargo/bin:/tools/mise/shims:${PATH}"
