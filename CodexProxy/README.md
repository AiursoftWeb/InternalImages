# CodexProxy image

The image installs the Python package from `source/`. Building it does not fetch
source from another Git repository or require GitLab credentials.

The source was imported from `ZeTian/codex-proxy` revision
`a6dd9e90bd7747eb0508c7a2d959cc49e32ffa07`, the revision previously used by this
Dockerfile. Its existing configurable request-size patch is included directly in
`source/codex_proxy/server.py`. The original snapshot did not include a license file. The upstream author has since
[added the MIT license](https://github.com/wowyuarm/codex-proxy/issues/2#issuecomment-6431931512).
The upstream copyright and license are preserved in `source/LICENSE` and in the
image at `/usr/share/doc/codex-proxy/LICENSE`.

Make future source changes here and run the existing tests in `source/tests/`.
The image's authentication wrapper, startup patches, environment variables and
persistent data paths are unchanged.
