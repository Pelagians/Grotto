# ChatGPT Desktop sandbox investigation

Status: unresolved as of 2026-07-16. This document records live evidence from
the Grotto ChatGPT Desktop container. It does not select a fallback or weaken
the active permission profile.

## Security boundary

The outer runtime remains a rootless Podman container running as 'abc', with
SELinux enforcing, normal Podman seccomp, and ':Z' labels on persistent mounts.
The investigation does not require privileged mode, 'CAP_SYS_ADMIN',
'label=disable', or unconfined seccomp.

Direct commands in the graphical terminal work. The failure is in the nested
Bubblewrap sandbox that Codex uses for tool-mediated commands.

## Live inventory

The tested image reported:

| Item | Live value |
| --- | --- |
| Identity | 'uid=1000(abc) gid=1000(abc)', groups 'sudo', 'users', 'docker', 'abc' |
| Distribution | Debian GNU/Linux 13 (trixie) |
| Host kernel | '7.0.12-201.fc44.x86_64' |
| Process context | 'system_u:system_r:container_t:s0:c357,c376' |
| Seccomp | mode '2', one filter |
| User namespaces | enabled; 'unshare --user --map-root-user true' succeeds |
| Codex CLI | '0.144.5' |
| Bundled Bubblewrap | 'bubblewrap built for Codex' |
| System Bubblewrap used for comparison | Debian '0.11.0' |
| '/workspace' | private XFS bind mount, read/write, SELinux labeled |
| '/config' | private XFS bind mount, read/write, SELinux labeled |
| '/tmp' | container overlay filesystem |
| '/dev/shm' | 2 GiB |
| Wrapper revision | '52e9701e3f1be291821cff904b6cd4bdce30998d' |
| Desktop version | '26.707.91948' |
| Desktop DMG SHA-256 | '5a2ab9689f4ba38fcb135565246d5ca2f124d539336a0a32afcdb72040d21466' |

The top-level Containerfile is not a complete package inventory because the
LinuxServer Selkies base supplies additional tools.

## Direct execution

The graphical shell path succeeds:

~~~console
$ /bin/true
$ echo "direct shell works"
direct shell works
$ git --version
git version 2.47.3
$ python3 --version
Python 3.13.5
$ /opt/chatgpt/resources/node-runtime/bin/node --version
v22.22.2
~~~

The Node runtime is image-managed under
'/opt/chatgpt/resources/node-runtime'; it was not initially on the PATH of the
independent diagnostic subprocess.

## Bubblewrap primitive results

The Codex helper used in the exact commands was:

~~~bash
BWRAP=/opt/codex-cli/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/codex-resources/bwrap
~~~

A basic namespace and read-only root succeeds:

~~~bash
"$BWRAP" \
  --unshare-user \
  --unshare-pid \
  --ro-bind / / \
  /bin/true
~~~

Exit status: '0'.

A fresh Bubblewrap '/dev' fails:

~~~bash
"$BWRAP" \
  --unshare-user \
  --unshare-pid \
  --ro-bind / / \
  --dev /dev \
  /bin/true
~~~

Exit status: '1'.

~~~text
bwrap: Can't mount devpts on /newroot/dev/pts: Permission denied
~~~

### Smallest protected-child reproduction

A normal read-only bind of an existing child succeeds, including on the outer
XFS mounts:

~~~bash
mkdir -p /workspace/.grotto-bwrap-matrix/.git
"$BWRAP" \
  --unshare-user \
  --unshare-pid \
  --ro-bind / / \
  --bind /workspace/.grotto-bwrap-matrix /workspace/.grotto-bwrap-matrix \
  --ro-bind /workspace/.grotto-bwrap-matrix/.git /workspace/.grotto-bwrap-matrix/.git \
  /bin/true
~~~

Exit status: '0'.

Codex also protects metadata names that do not exist yet, so an ordinary
read-only bind is not sufficient to reproduce its failing operation. The
smallest equivalent command is:

~~~bash
mkdir -p /workspace/.grotto-bwrap-remount-git
"$BWRAP" \
  --unshare-user \
  --unshare-pid \
  --ro-bind / / \
  --bind /workspace/.grotto-bwrap-remount-git /workspace/.grotto-bwrap-remount-git \
  --perms 555 \
  --tmpfs /workspace/.grotto-bwrap-remount-git/.git \
  --remount-ro /workspace/.grotto-bwrap-remount-git/.git \
  /bin/true
~~~

Exit status: '1'.

~~~text
bwrap: Can't remount readonly on /newroot/workspace/.grotto-bwrap-remount-git/.git: Unable to remount destination "/newroot/workspace/.grotto-bwrap-remount-git/.git" with correct flags: Permission denied
~~~

This distinction matters: existing read-only child binds work; the failure is
the legacy remount of a newly mounted synthetic tmpfs used to prevent creation
of an absent protected path.

### Filesystem and protected-name matrix

Each row was tested with the Codex-bundled helper and '/bin/true'. The
write-without-protection case also created and removed an ordinary file.

| Backing path | Ordinary workspace write | Existing child '--ro-bind' | Synthetic '.git' remount | Synthetic '.agents' remount | Synthetic '.codex' remount |
| --- | --- | --- | --- | --- | --- |
| '/workspace' (XFS bind) | pass | pass | 'EACCES' | 'EACCES' | 'EACCES' |
| '/config' (XFS bind) | pass | pass | 'EACCES' | 'EACCES' | 'EACCES' |
| '/tmp' (container overlay) | pass | pass | 'EACCES' | 'EACCES' | 'EACCES' |

A symlinked '.git' source also passed when mounted with '--ro-bind' in all three
locations. The failure therefore does not depend on the XFS volume backing,
one protected name, or an ordinary child bind. It follows the synthetic
tmpfs-plus-remount operation.

A workspace without any protected remount operation is writable. However,
Codex's built-in ':workspace' profile automatically protects '.git', '.agents',
and '.codex' under each writable root even when those paths are absent. An
empty directory therefore still reaches the synthetic remount path.

## Syscall isolation

'strace' showed the failing Bubblewrap syscall:

~~~text
mount("tmpfs", ".../.git", "tmpfs", MS_NOSUID|MS_NODEV, "mode=0555") = 0
mount("none", ".../.git", NULL,
      MS_RDONLY|MS_NOSUID|MS_NODEV|MS_REMOUNT|MS_BIND|MS_SILENT|MS_RELATIME,
      NULL) = -1 EACCES (Permission denied)
~~~

The same result occurs with the Codex helper and Debian Bubblewrap 0.11.0.

A minimal program using the same legacy 'mount(2)' remount flags also returns
'EACCES' inside a nested user namespace. In contrast, util-linux performs the
equivalent read-only transition with the newer mount API:

~~~text
open_tree(..., OPEN_TREE_CLOEXEC) = 3
mount_setattr(3, "", AT_EMPTY_PATH,
              {attr_set=MOUNT_ATTR_RDONLY|MOUNT_ATTR_NOSUID|MOUNT_ATTR_NODEV, ...},
              32) = 0
~~~

This succeeds with the same outer process context and seccomp filter. It
establishes that normal mounts and read-only transitions are not globally
blocked, and identifies Bubblewrap's legacy remount operation as the failing
primitive.

The fresh devpts problem is separate. Both legacy 'mount(2)' and a direct
'fsopen'/'fsconfig' attempt to create a new devpts instance return 'EACCES'.
Updating only the protected-path remount to 'mount_setattr' would not solve the
fresh '/dev' failure.

## Device exposure

Bubblewrap's fresh '/dev' setup creates a new tmpfs, binds only these outer
device nodes into it, creates standard fd symlinks, and then mounts a private
devpts instance:

- '/dev/null'
- '/dev/zero'
- '/dev/full'
- '/dev/random'
- '/dev/urandom'
- '/dev/tty'
- '/dev/stdin', '/dev/stdout', '/dev/stderr', '/dev/fd', and '/dev/core'
- private '/dev/pts'

Binding the complete outer '/dev' also exposes runtime mounts and directories
that are not in that minimal set. In the live container these included
'/dev/input', '/dev/mqueue', '/dev/shm', and the outer '/dev/pts' instance.
Sharing the outer devpts instance can expose other terminal device nodes to
same-user processes. Consequently, replacing '--dev /dev' with
'--dev-bind /dev /dev' is not selected by this change.

## Codex backend results

The official CLI surface produced:

| Check | Result |
| --- | --- |
| 'codex sandbox -P :read-only ... /bin/true' | fails at fresh devpts |
| 'codex sandbox -P :workspace ... /bin/true' | fails at fresh devpts; after a whole-'/dev' diagnostic bind it fails at protected remount |
| '--enable use_legacy_landlock' with ':read-only' | passes |
| '--enable use_legacy_landlock' with ':workspace' | exits 101 and rejects direct-runtime-enforcement profiles |

The Landlock workspace error is:

~~~text
permission profiles requiring direct runtime enforcement are incompatible with --use-legacy-landlock
~~~

Landlock therefore remains a useful read-only diagnostic, not a secure
workspace-write fallback for the active profile.

## SELinux AVC correlation

The mount matrix ran during these UTC windows:

- '2026-07-16T22:02:55.310438098Z' through
  '2026-07-16T22:02:55.635262572Z'
- '2026-07-16T22:03:40.396991884Z' through
  '2026-07-16T22:03:40.684550476Z'

The outer host audit stream is not exposed inside this rootless container:

- '/var/log/audit/audit.log' is absent;
- '/sys/fs/selinux' is replaced by crun's read-only empty-directory mask;
- 'auditctl -s' lacks the required host audit capability;
- the container journal and dmesg contain no host AVC records.

No matching AVC could therefore be collected from inside the container.
'EACCES' alone is not treated as proof of an SELinux denial. Correlation must be
performed on the Fedora host for the same test interval, for example:

~~~bash
sudo ausearch \
  -m AVC,USER_AVC,SELINUX_ERR \
  -ts 22:02:50 \
  -te 22:04:00 \
  -i
~~~

A new reproduction should record fresh UTC boundaries and query the host with
those timestamps.

## Architecture candidates

No candidate below is enabled by the diagnostics PR.

1. **Upstream synthetic-mask change.** A read-only bind of an existing empty
   directory works on every tested backing filesystem and preserves the
   protected-path rule. Codex could use a trusted empty-directory source
   instead of tmpfs plus '--remount-ro' for missing protected directories.
   This still leaves fresh devpts unresolved.
2. **Upstream Bubblewrap/container support.** Bubblewrap could use a compatible
   read-only mount operation where possible, but devpts requires a separate
   design. This should be solved upstream and tested without changing outer
   confinement.
3. **Managed outer read-only child mounts.** Operator-provided read-only mounts
   for existing metadata work, but do not scale to absent protected paths,
   '/tmp', arbitrary projects, or Git worktree '.git' files without substantial
   deployment coordination.
4. **Managed worktree layout.** Keeping Git metadata outside the writable tree
   helps '.git', but does not by itself protect missing '.agents' and '.codex'
   names or the writable temp roots.
5. **Minimal device compatibility layer.** Reconstructing only Bubblewrap's six
   device nodes avoids exposing '/dev/input', '/dev/mqueue', and '/dev/shm', but
   private PTY allocation still requires a permitted devpts design. Binding the
   outer devpts instance changes isolation and needs explicit review.

The safe image changes deliberately stop at diagnostics, workbench
dependencies, persistent paths, and reproducibility metadata. There is no
automatic fallback and no protected-path exception.
