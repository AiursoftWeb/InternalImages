"""构建时修复 Copilot 合成的 Responses 工具项 ID，不修改上游源码快照。"""

import sys
from pathlib import Path

_ANCHOR = '''        new_item = dict(item)
        if "content" in new_item:
'''
_REPLACEMENT = '''        new_item = dict(item)
        # Copilot 可能用 fc_ + call_id 重建可选的工具项 ID；上游不兼容此 ID。
        # 仅移除这种合成 ID，保留真正关联工具结果的 call_id 及其他字段。
        call_id = new_item.get("call_id")
        if (
            new_item.get("type") == "function_call"
            and isinstance(call_id, str)
            and call_id
            and new_item.get("id") == "fc_" + call_id
        ):
            new_item.pop("id")
        if "content" in new_item:
'''


def apply_patch(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if source.count(_ANCHOR) != 1:
        raise RuntimeError("Responses 补丁锚点不唯一或不存在，请检查上游源码")
    path.write_text(source.replace(_ANCHOR, _REPLACEMENT, 1), encoding="utf-8")


if __name__ == "__main__":
    apply_patch(Path(sys.argv[1]))
