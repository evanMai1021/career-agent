"""兼容原有入口；实际实现见 career_agent.services.file_import_server。"""

import sys
import career_agent.services.file_import_server as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    # 导入也转交同一模块，避免两份状态或测试替身失效。
    sys.modules[__name__] = _implementation
