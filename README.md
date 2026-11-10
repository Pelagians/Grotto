# Grotto

Grotto publishes ready-to-run container images for AI applications, agents,
and desktop workbenches you can host on your own infrastructure. Each image
packages an upstream application with the tools and dependencies it needs.
The deployment guides show what to mount so your data can survive image
replacement.

## Choose an image

Pick the application you want to run and follow its guide for setup,
configuration, and storage.

| Image | Use it for | Guide |
| --- | --- | --- |
| `ghcr.io/pelagians/grotto-openclaw:latest` | An OpenClaw gateway with baseline tools and persistent user-installed tools | [First launch with Podman](docs/openclaw.md#first-launch-with-podman) |
| `ghcr.io/pelagians/grotto-chatgpt-desktop:latest` | A browser-streamed ChatGPT and Codex desktop workbench | [ChatGPT Desktop](docs/chatgpt-desktop.md#run-with-intel-or-amd-graphics) |
| `ghcr.io/pelagians/grotto-hermes:latest` | A Hermes Agent backend with persistent tools and agent state | [Hermes deployment and storage](docs/hermes.md) |
| `ghcr.io/pelagians/grotto-hermes-desktop:latest` | A streamed Hermes Desktop client for an existing Hermes backend | [Hermes Desktop setup](docs/hermes-desktop.md) |
| `ghcr.io/pelagians/grotto-openadapt-teach:latest` | An experimental OpenAdapt Teach worker that attaches to a browser you provide | [Teach worker setup](docs/openadapt-teach.md) |

The [image matrix](docs/image-matrix.md) lists ports and persistent paths for
each image. For example, OpenClaw stores configuration under `/config`, the
Hermes backend uses `/opt/data`, and the Teach worker uses temporary storage.
Mount the paths documented for your image before you run it.

## Build an image

Use a supported container engine and the targets in the [Makefile](Makefile).
For example, `make image-openclaw` builds the OpenClaw image locally.
[GitHub Actions](.github/workflows/build.yml) checks builds on pull requests
and publishes images from release and rebuild workflows.

When adding an image, preserve the upstream interface where practical.
Document the required ports, storage, authentication, and upgrade steps.
Supply credentials at runtime.

## Maintained by Pelagian

Grotto images run independently of the Pelagian platform. For other layers
of the stack, see [Current](https://github.com/Pelagians/Current) for Linux
system images and [Cage](https://github.com/Pelagians/Cage) for Windows
applications on Linux.

## License

See [LICENSE](LICENSE) for Grotto source licensing. Packaged upstream applications retain their own licenses and distribution terms.
