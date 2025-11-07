# BRT Data Forwarder

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Tags](https://img.shields.io/docker/v/funnyzak/brt-data-forwarder?sort=semver&style=flat-square)](https://hub.docker.com/r/funnyzak/brt-data-forwarder/)
[![Image Size](https://img.shields.io/docker/image-size/funnyzak/brt-data-forwarder)](https://hub.docker.com/r/funnyzak/brt-data-forwarder/)

轻量级 Flask 服务，用于接收专有格式的环境传感器数据、进行必要的纠错与缓存，并按顺序转发到多个下游 HTTP 终端。内置线程安全的内存缓存、可配置的认证 / 时间戳 / 重试策略，以及开箱即用的健康检查与设备查询 API。

## 功能亮点
- **多终端串行转发**：按照配置顺序 POST 数据，支持每个目标独立超时、可选重试与延迟。
- **智能缓存**：特殊指标遇到 `FFFF/FFFE` 等无效值时，用历史有效值回填；内存缓存定期原子持久化到 `data/cache.json`。
- **时间戳控制**：可在接收侧重置 `time`、`scan_time`，并追加 `received_at` 字段，便于追踪链路时延。
- **双路认证**：同时支持 URL 查询参数与 HTTP Header，满足不同客户端限制。
- **统一配置入口**：`config.yaml` 描述全部行为，任意键都可被 `BRT_` 前缀的环境变量覆写，适合容器化部署。
- **完善的可观测性**：`/health` 暴露版本与运行时长，`/api/device/<ble_addr>` 可查看缓存值，RotatingFileHandler 负责日志轮转。

## 工作原理
1. `POST /receive_brt_data` 接收 JSON 负载（网关上报数据 + 设备指标）。
2. 根据 `processing` 与 `timestamp` 配置修正时间戳、回填无效指标，并刷新内存缓存。
3. 串行向 `forwarder.targets` 列表转发，失败时可依配置重试。
4. 缓存后台线程按 `sync_interval` 将脏数据落盘，进程退出时强制同步。

## 快速开始
### 环境
- Python 3.7+
- pip / venv（推荐）

### 安装
1. 克隆仓库并进入目录。
2. （可选）`python -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. `cp config.yaml.example config.yaml`，根据实际环境编辑。
5. `python forwarder.py -c config.yaml` 启动；若省略 `-c`，默认读取根目录的 `config.yaml`。
6. 使用 `python forwarder.py --version` 查看当前版本（0.0.3）。

`data/` 与 `logs/` 会在首次运行时自动创建，缓存与日志分别保存在 `data/cache.json` 与 `logs/forwarder.log`。

## 配置概览
```yaml
server:
  host: "0.0.0.0"
  port: 8080
receiver:
  path: "/receive_brt_data"
  auth:
    enabled: true
    query_param: "auth_token"
    header: "Authorization"
    valid_tokens: ["your-secret-token-123"]
processing:
  enabled: true
timestamp:
  reset_on_receive: true
  reset_fields: ["time", "scan_time"]
  add_receive_timestamp: true
  receive_timestamp_field: "received_at"
forwarder:
  targets:
    - { url: "https://example.com/api", timeout: 5 }
  retry:
    enabled: true
    max_attempts: 1
cache:
  type: "memory"
  file_path: "./data/cache.json"
  sync_interval: 30
  special_metrics: [co2, hcho, lux, uva_class, uva_raw, voc]
  invalid_patterns: ["FFFF", "FFFE"]
logging:
  level: "INFO"
  file_path: "./logs/forwarder.log"
```

关键字段说明：
- `server`：Flask 启动参数，`debug` 会开启热重载与详细日志。
- `receiver`：接收端路径与认证方式；两个 token 校验入口任一命中即通过。
- `processing.enabled`：关闭时仍更新缓存但不替换无效值，常用于调试或需要原始报文的场景。
- `timestamp`：允许重置网关时间与扫描时间，或附加自定义接收时间字段。
- `forwarder.targets`：最少配置一个 URL，可根据目标对 `timeout` 做精细化控制；`retry.max_attempts` 表示额外重试次数。
- `cache`：当前实现为内存 + JSON 持久化，`special_metrics` 列表控制需要进行无效值检查的指标。
- `logging`：RotatingFileHandler 配置，便于长期运行。

### 环境变量覆盖
任意配置都可通过环境变量重写，命名规则：`BRT_<路径>`，路径使用双下划线区分层级，并保持小写。例如：
```bash
export BRT_SERVER__PORT=9090
export BRT_RECEIVER__AUTH__VALID_TOKENS__0=my-token
export BRT_FORWARDER__TARGETS__0__URL=https://upstream.example.com/post
export BRT_PROCESSING__ENABLED=false
```
类型会按照原始值自动转换（bool/int/float），未匹配的值保持字符串。

## API
| 方法 | 路径 | 描述 | 认证 |
| ---- | ---- | ---- | ---- |
| POST | `/receive_brt_data` | 接收并转发传感器数据，返回每个目标的转发结果 | 可选，取决于配置 |
| GET | `/api/device/<ble_addr>` | 返回缓存中某个设备的指标及时间戳 | 同接收端 |
| GET | `/health` | 返回 `{status, version, uptime}` | 无 |

示例请求：
```bash
curl -X POST "http://localhost:8080/receive_brt_data?auth_token=your-secret-token-123" \
     -H "Content-Type: application/json" \
     -d '{
           "seq_no": 1,
           "time": 1758615013,
           "devices": [{
             "ble_addr": "E7E8F5F8C9A4",
             "scan_time": 1758615011,
             "co2": "0234",
             "voc": "FFFF"
           }]
         }'
```

返回示例：
```json
{
  "success": true,
  "message": "Data received and forwarded",
  "forward_results": [
    {"url": "https://example.com/api", "success": true, "attempts": 1}
  ]
}
```

`GET /api/device/E7E8F5F8C9A4` 将输出缓存的指标值与 `updated_at`/`scan_time`，若未命中则返回 404。

## 缓存与数据处理策略
- `MemoryCacheWithPersistence` 通过 `threading.RLock` 确保并发安全，脏数据由后台线程按 `sync_interval` 批量落盘，退出时会强制 `force_sync()`。
- 对 `special_metrics` 中的字段：
  - 值匹配 `invalid_patterns` 时（默认 `FFFF/FFFE`），若 `processing.enabled` 为 `true` 则尝试回填缓存值；未命中则保留原值并记录日志。
  - 其它有效值会立即写入缓存，包括其 `scan_time` 与 `updated_at`。
- 提供 `cleanup_expired_data(max_age_days)` 以便未来扩展定期清理逻辑（当前需手动调用）。

## 测试与调试
- 运行 `python test_client.py` 可一次性验证健康检查、接收端（Query/Header 双模式）、设备查询以及无效值缓存逻辑。
- 也可使用 `curl`/Postman 等工具根据上述 API 文档手动测试。
- 观察 `logs/forwarder.log` 了解转发、缓存、认证等详细过程；日志具有轮转能力（默认 10MB × 7 份）。

## 项目结构
```
brt-data-forwarder/
├── forwarder.py           # 主服务与缓存实现
├── test_client.py         # 集成测试脚本
├── config.yaml.example    # 配置模板
├── config.yaml            # 样例配置（自定义）
├── requirements.txt       # 依赖声明
├── data/                  # 缓存持久化（运行时自动生成）
├── logs/                  # 日志输出目录（运行时自动生成）
└── README.md
```

## 许可证
本项目以 [MIT License](LICENSE) 发布，可自由修改与分发。
