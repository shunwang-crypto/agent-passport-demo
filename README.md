# Agent Passport Demo

面向企业办公多智能体协作场景的安全验证 Demo。项目重点不是单独做一个智能体应用，而是在一条真实办公任务链路中验证四件事：

- 智能体身份认证
- 最小权限授权
- 任务级委托令牌
- 全链路审计追踪

当前 Demo 以“生成销售周报并发送给授权经理”为主任务，同时内置多类异常与攻击场景，用来展示越权访问、错误目标发送、审批缺失、令牌篡改、重放攻击等问题如何被统一安全网关拦截。

## 项目亮点

- 真实多智能体链路：个人助理智能体、数据查询智能体、报表生成智能体、邮件发送智能体协作完成一个办公任务
- 统一安全网关：所有关键动作都经过认证、授权和委托校验
- 任务级委托：每次下游执行都依赖任务级能力令牌，支持单次使用、审批约束和撤销传播
- 审计可追溯：可以按任务查看任务流转、委托签发、访问校验和最终结果
- 竞赛展示友好：提供首页、资源边界、委托与令牌、安全评测、审计追踪等页面

## 适用场景

项目当前面向“多智能体安全协作验证”类竞赛或答辩展示，适合演示：

- 正常办公任务如何在最小权限约束下完成
- 跨部门越权查询如何被拦截
- 错误收件目标如何被拦截
- 高风险发送动作在缺少审批时如何被拒绝
- 委托撤销、委托重放、能力令牌篡改如何被识别

## 系统角色

- 业务用户：发起办公任务
- 个人助理智能体：拆解任务并签发下游委托
- 数据查询智能体：读取授权范围内的数据
- 报表生成智能体：根据查询结果生成报表
- 邮件发送智能体：向授权目标发送最终结果
- 授权网关：统一执行认证、授权、委托校验和审计记录

## 内置场景

### 真实协作场景

- `real_collaboration`
  读取销售数据，生成周报，并发送给授权经理

### 安全验证场景

- `unauthorized_query`
  跨部门数据越权
- `wrong_recipient`
  错误收件目标
- `revoked_access`
  撤权后继续执行
- `replay_attack`
  委托重放攻击
- `approval_missing`
  审批缺失
- `tampered_token`
  令牌签名篡改

### 批量评测

系统支持一键运行全部内置安全用例，并输出：

- 用例总数
- 符合预期数量
- 通过率
- 拦截率
- 每个用例的控制原因

## 页面说明

- 首页：展示当前任务结果、协作状态和关键产物
- 资源边界：展示资源目录、最小权限和初始授权规则
- 委托与令牌：展示任务级委托链、工作负载身份和令牌使用状态
- 安全评测：展示批量验证结果
- 审计追踪：按任务查看完整事件流水

## 目录结构

```text
feishucompete/
├─ agent_passport_demo/
│  ├─ audit.py
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

## 当前使用的运行目录

项目运行时使用 `workdir/` 作为真实工作目录：

- `workdir/docs/`：任务读取的文档与数据文件
- `workdir/tasks/`：任务模板文件
- `workdir/outputs/`：运行生成的报表、摘要和任务产物

当前实际输入文件示例：

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

如果本地命令不是 `python`，可以使用：

```powershell
py run_demo.py
```

启动后访问：

```text
http://127.0.0.1:8000
```

## 本地数据库说明

项目运行时会在根目录生成本地状态库：

- `agent_passport_state.db`

这个文件用于保存：

- 审计记录
- 委托账本
- 运行历史
- 资源与策略状态

它属于运行时本地状态，不属于源码本体，因此：

- 不需要手动创建
- 首次运行时会自动初始化
- 不应提交到 GitHub

## 环境要求

- Python 3.11+
- 当前实现主要依赖 Python 标准库

## 在线模型配置

如需接入在线模型，可配置以下环境变量：

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


## 已知边界

- 当前存储配置面向 Demo 展示，不是生产级持久化方案
- 当前重点是安全验证链路完整，而不是大规模工程化部署
