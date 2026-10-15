"""兼容原有入口；实际实现见 career_agent.services.api_app。"""

import sys
import career_agent.services.api_app as _implementation


# HTTP 服务仍由 Uvicorn 启动；此文件只兼容原 api_app:app 入口。
sys.modules[__name__] = _implementation
