# Alyrra QQ 群机器人

接收平台推送的全群文字与图片消息，支持不用 @也能接话，使用 Vertex AI gemini-3.8-flash。
完整设定在 Alyrra.md；调用使用压缩版 Alyrra.runtime.md，修改设定时应同步修改它。
程序显式使用 Google Cloud 默认凭据 ADC，不使用 API Key。

## 安装与启动

需要 Python 3.11 或更新版本、Google Cloud CLI，以及已创建并加入群的 QQ 官方机器人。
使用 WebSocket 接收事件；全群模式需要平台允许推送全量群消息。

```powershell
git clone https://github.com/Doraemon-Lam/Alyrra_bot.git
cd Alyrra_bot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item runtime_config.example.json runtime_config.json
gcloud auth application-default login
```

在 .env 中填写自己的 QQ_BOT_APPID、QQ_BOT_APPSECRET、GOOGLE_CLOUD_PROJECT。
凭据通过 Google ADC 配置，不要把服务账号密钥文件放进仓库。

1. 在 .env 中填写新的 QQ_BOT_APPSECRET。QQ WebSocket 保持开启。
2. 如需重新登录 Google，执行 gcloud auth application-default login。
3. 在 PowerShell 执行：

```powershell
.\.venv\Scripts\python.exe bot.py --check
.\.venv\Scripts\python.exe bot.py
```

出现“已连接 QQ”后，群里发送 @Alyrra 你好。保持终端和电脑运行，按 Ctrl+C 停止。

## 聊天记忆

按群隔离，暂存每群最近 60 条消息；请求携带最近半小时最多 20 条、4000 字。
只保存在内存，重启清空。@Alyrra 清空记忆 或 /reset 清空当前群的共享短期记忆。
平台必须开启全量群消息能力；只能读取平台实时推送的消息，不能拉取加入前的历史。
支持图片理解，不支持语音。只读取 QQ 图片域名，单文件最多 8 MB，最长边缩至 768 像素。
一次最多 2 张，以低媒体分辨率理解；小字可能看不清。相同图片的内容描述缓存避免重复上传。

## 节省调用与限流

runtime_config.json 设为 mode=active 时，每批普通消息和图片都进入回复流程，
1 秒合并连发，不选择沉默，取消本地分钟、小时、每日调用和 token 限额。
并发仍为 1，保留短上下文和图片缓存；调用期间的新消息合并成下一批。
云端配额仍然有效，实际费用按使用量计算。实时切换 mode=economy 即恢复下列省钱策略。

- 所有收到的消息先存入本地缓冲，不直接调用模型。
- @消息、提到 Alyrra/艾璃拉/艾璃、新图片或累计 10 条新消息才触发候选。
- 候选等待 3 秒合并连发；普通接话每群至少间隔 120 秒。
- 单次模型请求同时判断是否回复、识图和生成回复；选择沉默也消耗 token。
- LOW 思考级别、1024 输出 token 上限；输出包含思考 token，不只是可见回复。
- 全局每分钟最多 4 次；主动判断每小时最多 12 次、每天 48 次；总计每天最多 200 次。
- 每日 token 预算默认 500000，失败请求保守预留 12000 token。
- 每日调用和 token 计数写入 usage.json，按北京时间换日，重启不清空。
- 分钟和小时限流在内存；重启会清空短窗口，但不会清空日限额。
- 并发为 1，不无限堆积请求；失败后暂停新模型请求 60 秒。
- 日志显示调用类型、token 用量与 QQ 发送结果，不打印消息正文。

已设置 SDK 请求尝试次数为 1，避免应用层自动反复重试。日 token 预算是应用侧估算门槛，
不是云账单硬上限；图片解析失败或缺少用量元数据时保守保留预留值。
使用专属测试群，或在 ALLOWED_GROUP_OPENIDS 中填入需要启用的群 openid。

## 配置

### 实时控制

runtime_config.json 每次接收消息、准备请求和发送回复前重新检查，保存后下次处理生效，无需重启。
该文件优先于 .env 的模式设置，适用于此进程连接的所有群。
mode 可选 active（积极）、economy（节省）、mentions（仅 @）、off（停止接收新聊天和回复）。
batch_seconds 为合并等待，cooldown_seconds 可选，未填写时积极模式 0 秒、节省模式 120 秒。
message_threshold 为节省模式普通消息触发条数，daily_calls/daily_tokens 为非积极模式日限额。
off 不删除已有记忆；已经发出的模型请求仍可能产生费用，但返回结果不会发送。

群里发送 /我的标识 获取自己的 member_openid，把它加入 admin_member_openids 数组后保存。
登记后可发 /模式 积极、/模式 节省、/模式 仅@、/模式 停止，以及 /冷却 30、/合并 3、/阈值 10。
推荐 @Alyrra 后输入控制指令；/状态 查看模式和今日用量。控制指令不调用模型。
QQ 群主身份不会自动获得此权限，使用本机明确配置的标识白名单。

### 记忆存储

群近期文字、图片地址、图片内容描述缓存均在 Python 进程内存，重启清空，不保存聊天数据库。
usage.json 保存日调用和 token 计数；member_names.json 保存登记称呼；runtime_config.json 保存控制设置。

名称优先使用成员通过“叫我小明”登记的称呼，其次使用事件自带的群名片/昵称。
QQ 事件未提供名称时使用“你”，不把内部编号当作昵称。称呼按群和成员绑定，
保存到 member_names.json，重启保留；登记称呼是本地操作，不调用模型。

.env.example 是配置样例。正式环境 QQ_BOT_SANDBOX=false；若后台明确使用沙箱，则改为 true。
ALLOWED_GROUP_OPENIDS 可限制群；日志中的 group_openid 是开放平台标识，不是 QQ 群号。
AppSecret 不要提交或发到聊天里。

## 重建环境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

新电脑需重新配置 ADC，并确认网络可访问 Google Cloud 和 QQ 开放平台。

## 图片生成

文字聊天与识图继续使用 gemini-3.8-flash。明确画图请求直接调用独立模型
gemini-3.1-flash-image，共用 Vertex 默认凭据，不先调用聊天模型分类。
IMAGE_MODEL 可在 .env 指定替代生图模型，修改该模型配置需重启。

```text
@Alyrra /画图 一只在月光森林里唱歌的精灵，水彩风格
帮我画一张蓝色蝴蝶
```

目前支持文字生成新图，不把群里任意对话或“你能画图吗”当成画图请求。
不自动使用群历史和图片作为生图参考。每次返回并发送一张 1K 方形图片。
先回“开始画”，再通过 QQ 本地 base64 上传，取得 file_info 后发送富媒体消息。
若 QQ 上传失败，结果仍保存在 generated_images 中，无需重新生成。
generated_images 不自动清理，按需删除旧图片即可。

runtime_config.json 支持实时设置 image_enabled、image_daily_calls、image_cooldown_seconds。
默认开启、每天最多 10 次、每位成员间隔 60 秒，全局同时只画 1 张，忙时不排队。
失败调用也计入 image_usage.json 的日计数，重启不会清空。
此限额独立于聊天限额，积极聊天模式不会绕过画图上限。
停止聊天模式会禁止新的画图请求；关闭画图时已发出的请求仍可能产生费用。

管理员可以在群里执行：

```text
@Alyrra /画图开关 开启
@Alyrra /画图开关 关闭
@Alyrra /画图上限 5
```

生图模型以图片输出计费，token 计数不能直接按聊天模型单价估算。
新模型需项目有相应调用权限；群里发送图片还需 QQ 富媒体权限。

## 排查

- 启动缺少凭据：重新执行 gcloud auth application-default login。
- QQ 登录失败：检查 AppID、最新 AppSecret 以及沙箱模式。
- 收不到事件：检查 QQ 后台群消息事件权限、服务范围和体验成员设置。
- 收到事件但回复失败：检查 Vertex 权限、网络、配额与 QQ 消息权限。
