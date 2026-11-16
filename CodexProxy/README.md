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

## Copilot Responses 兼容补丁

镜像构建时先运行 `patch_responses.py`，再安装包；不修改 `source/` 快照。
补丁仅在 Responses 输入项的 `type` 为 `function_call`、`call_id` 为非空字符串，
且可选 `id` 恰好等于 `"fc_" + call_id` 时省略该 `id`。
保留 `call_id`、工具参数和结果，保留其他 ID，不依赖 ID 长度，也不修补响应输出。
这是对已复现的 Copilot 合成 ID 与上游兼容性问题的规避，不代表已证实上游内部原因。
补丁锚点缺失或不唯一时构建会失败，避免源码更新后静默失效。

`test_responses_patch.py` 覆盖实际打补丁后的规范化和流式、非流式请求处理。
运行时使用 `pytest -c CodexProxy/source/pyproject.toml CodexProxy/test_responses_patch.py`。
原有 server/translator 测试应同时针对打补丁后的包运行，以验证回归。
