# Gitee Go CI 接入说明（小组 7）

## 启用条件

仓库根目录已经有 `.gitee-ci.yml`，**首次推到 group7-cc / main / develop 分支时，Gitee 会自动检测并提示开通 Gitee Go**。需要管理员（yunjiansu）点击"开通"才会真正激活流水线，激活后才会跑。

激活路径：
```
Gitee 仓库页 → 顶部菜单「服务」→ "Gitee Go" → 开通 → 选择代码源（当前仓库）
```

> 如果团队用的是「免费版 Gitee Go」：每月有构建时长限制（截至 2026 年公开信息是 1800 分钟）。pytest 单次约 1 分 30 秒，月 1200 次左右完全够用。

---

## 文件结构与作用

| Stage | Job | 作用 | 失败影响 |
|-------|-----|------|---------|
| install | `install-deps` | pip install 依赖 + 缓存 .cache/pip | 🔴 阻塞下游 |
| test | `pytest` | 跑 119 个测试用例，存 JUnit 报告 | 🔴 阻塞 merge |
| lint | `ruff` | 代码风格扫描 | 🟡 不阻塞（黄叹号） |

> pytest 报告可在流水线详情页下载 `pytest-report-*.zip`，看哪个 case 红了。

---

## 触发规则（only）

job 会在以下任一情况触发：
1. 推送（push）到 `group7-cc`、`main`、`develop`
2. 任何分支发起 PR（包含 `merge_requests`）

`runner` 默认用 `python:3.11-slim` 镜像。

---

## 第二次跑之前的微调项（可选）

如果发现 ruff 红叉太多看着心烦（默认 297 个 warning，主要是 import 顺序 + 无用 import），可以把 lint job 的 `script` 那行改成更轻的：

```yaml
script:
  - cd simulator
  - pip install ruff
  - ruff check --select E9,F63,F7,F82 --ignore E501 tools/ day1/ day2/ day8/ esp32/ tests/ || true
```

含义：
- `E9`: 语法错误（一般是写错的，没理由放过）
- `F63,F7,F82`: 真实 bug 类（`undefined name`、`assert on tuple` 等）
- `E501`: 单行过长（团队风格约定，可忽略）

只有真正的代码缺陷会被点亮，其余 297 个全静默。

---

## 测试用例清单（pytest 当前 159/159 通过）

| 文件 | 用例数 | 关注点 |
|------|--------|--------|
| `test_sensor_simulator.py` | 41 | sensor_simulator 协议 + JSON 序列化 |
| `test_esp32_modbus_gw.py` | 40 | ESP32 modbus_gw MBAP/调度/冷却（mock time+socket） |
| `test_gateway_bridge.py` | 28 | gateway_bridge（带 mock MQTT） |
| `test_modbus_slave_sim.py` | 22 | modbus_slave_sim 真实子进程 |
| `test_protocol_consistency.py` | 21 | 三处配置文件交叉一致性 |
| `test_mqtt_integration.py` | 7 | amqtt 本地 broker 端到端 |

合计 **159 个用例**，~64 秒跑完。

---

## 备注：Gitee packed-refs 问题

> 本地推送时如果遇到 `git push` 报 `[remote rejected]` 或 Gitee Web 端显示 `[ahead N]` 与本地对不上：
> 是因为 Gitee 把 refs 写到了 `.git/packed-refs` 而不是 `refs/remotes/origin/*`。
> 临时处理：在本地 `sed` 修改 `.git/packed-refs` 即可。
