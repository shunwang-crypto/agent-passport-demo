# 智能体通行证网关 Demo

面向企业办公多智能体协作场景的安全验证 Demo。项目重点不是单独做一个 Agent 应用，而是在一条真实办公任务链路中验证四件事：

- 智能体独立身份
- 最小权限授权
- 任务级令牌委托
- 全链路审计追踪

当前 Demo 以“生成销售周报并发送给授权经理”为主任务，同时内置多类异常与攻击场景，用于展示跨部门越权、错误收件目标、审批缺失、令牌篡改、令牌重放、任务撤权、委托超时等问题如何被统一安全网关拦截。

## 项目定位

这个项目适合以下用途：

- 多智能体安全方向竞赛 Demo
- 安全答辩或作品演示
- 展示“身份认证 + 授权控制 + 令牌委托 + 审计闭环”的完整链路

项目不是通用 Agent 平台，也不是生产级 IAM 系统。当前版本是面向展示和验证的可运行原型。

## 核心能力

### 1. 智能体独立身份

系统中的每个执行主体都以独立工作负载身份运行，不直接复用业务用户身份。

### 2. 最小权限授权

不同智能体只拥有完成当前职责所需的最小权限。例如：

- 个人助理智能体：负责拆解任务与签发下游令牌
- 数据查询智能体：只允许读取授权数据集
- 报表生成智能体：只允许根据查询结果生成报表
- 邮件发送智能体：只允许向授权目标发送最终结果

### 3. 任务级一次性令牌

下游动作依赖任务级能力令牌执行，支持：

- 单次消费
- 审批约束
- 有效期限制
- 撤权传播
- 过期失效

### 4. 全链路审计追踪

每次任务的发起、委托签发、访问校验、策略拒绝和最终结果都会进入审计账本，可按任务回放。

## 内置场景

### 正常办公链路

- `real_collaboration`
  读取销售部第 15 周业务数据，生成周报，并发送给授权经理邮箱。

### 安全验证场景

- `unauthorized_query`
  跨部门数据越权查询
- `wrong_recipient`
  错误收件目标
- `revoked_access`
  撤权后继续访问
- `replay_attack`
  委托令牌重放
- `approval_missing`
  高风险发送缺少审批
- `tampered_token`
  能力令牌签名篡改
- `delegation_timeout`
  委托超时失效

### 批量评测

系统支持一键运行全部内置用例，并输出：

- 用例总数
- 符合预期数量
- 通过率
- 拦截率
- 每个用例的最终控制原因

## 页面说明

- 首页：展示当前任务结果、核心能力、最近运行和主要入口
- 资源边界：展示资源目录、权限边界和可签发范围
- 委托与令牌：按任务展示令牌链路、令牌状态和终止原因
- 安全评测：展示批量验证结果与各场景状态
- 审计追踪：按任务查看事件流水和控制结果

## 目录结构

```text
feishucompete/
├─ agent_passport_demo/
│  ├─ audit.py
│  ├─ benchmark.py
│  ├─ capability.py
│  ├─ data.py
│  ├─ delegation.py
│  ├─ file_store.py
│  ├─ frontend.py
│  ├─ gateway.py
│  ├─ llm_client.py
│  ├─ models.py
│  ├─ policy.py
│  ├─ prompts.py
│  ├─ real_flow.py
│  ├─ registry.py
│  ├─ storage.py
│  └─ dashboard/
│     ├─ exporter.py
│     ├─ presenters.py
│     ├─ router.py
│     ├─ service.py
│     └─ views.py
├─ static/
├─ templates/
├─ workdir/
│  ├─ docs/
│  ├─ tasks/
│  └─ outputs/
├─ run_demo.py
├─ .gitignore
└─ README.md
```

## workdir 说明

运行时使用 `workdir/` 作为本地工作目录：

- `workdir/docs/`：任务读取的文档和数据文件
- `workdir/tasks/`：任务模板文件
- `workdir/outputs/`：运行生成的摘要、报表和导出产物

当前主要输入文件包括：

- `workdir/docs/project_a_weekly.md`
- `workdir/docs/release_notes_april.md`
- `workdir/docs/risk_review.md`
- `workdir/docs/sales_week15.csv`
- `workdir/tasks/task_sales_report.md`

## 运行方式

在项目根目录执行：

```powershell
python run_demo.py
```

如果本机使用 `py` 启动 Python：

```powershell
py run_demo.py
```

启动后访问：

```text
http://127.0.0.1:8000
```

## 在线模型配置

如果要接入在线模型，请设置以下环境变量：

- `DEEPSEEK_ENABLED`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `DEEPSEEK_TIMEOUT_SECONDS`

PowerShell 示例：

```powershell
$env:DEEPSEEK_ENABLED = "true"
$env:DEEPSEEK_API_KEY = "<your_api_key>"
$env:DEEPSEEK_MODEL = "deepseek-chat"
python run_demo.py
```

说明：

- 未配置环境变量时，不应依赖本地硬编码密钥
- 提交到 GitHub 前不要把真实 API Key 写入仓库

## 本地状态文件

运行时会在根目录生成本地状态库：

- `agent_passport_state.db`

它用于保存：

- 审计记录
- 委托账本
- 运行历史
- 本地资源与策略状态

这个文件属于运行时状态，不属于源码本体：

- 首次运行会自动初始化
- 不需要手动创建
- 不应提交到 GitHub

## 环境要求

- Python 3.11+
- 当前实现主要依赖 Python 标准库

## 已知边界

- 当前存储与状态管理偏向 Demo 展示，不是生产级持久化方案
- 当前重点是安全验证链路完整，不是大规模工程部署
- 当前前端展示面向竞赛与答辩演示，仍有继续收口和统一文案的空间

## GitHub 提交建议

提交仓库前建议确认：

- 不提交 `agent_passport_state.db`
- 不提交 `artifacts/`
- 不提交 `workdir/outputs/`
- 不提交临时测试目录和本地渲染文件
- 不提交真实 API Key
