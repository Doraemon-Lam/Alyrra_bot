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
聊天上下文在内存，重启清空；总结用文字记录另存于本地 SQLite，重启保留。
@Alyrra 清空记忆 或 /reset 同时清空当前群内存上下文和总结用文字记录，不删除签到资料。
平台必须开启全量群消息能力；只能读取平台实时推送的消息，不能拉取加入前的历史。
支持图片和语音理解。只读取 QQ 媒体域名，单文件最多 8 MB，图片最长边缩至 768 像素。
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
也支持快捷指令 /积极、/节省、/仅@、/停止，权限与完整模式指令相同。
推荐 @Alyrra 后输入控制指令；/状态 查看模式和今日用量。控制指令不调用模型。
QQ 群主身份不会自动获得此权限，使用本机明确配置的标识白名单。

### 记忆存储

群上下文、图片地址和图片描述缓存位于内存；总结用文字记录在 alyrra.sqlite3，保留最多6小时、每群500条。
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
不自动使用群历史作为生图参考。明确画 Alyrra、艾璃拉或自画像时，附带 templates/assets/alyrra.jpg
作为形象参考；其他生图不附带。参考提高一致性，但无法保证生成结果完全一致。每次返回一张1K方形图片。
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

## 语音收发

用户语音（SILK/AMR/WAV/MP3 等）本地转换为 24 kHz 单声道 WAV，然后直接随聊天请求交给
gemini-3.8-flash 理解和回复，不额外调用转写模型。每次最多处理 1 段、60 秒；转写加入群短期记忆。
只有 QQ 平台实际推送可下载的语音附件时才可处理，不能读取被平台隐藏的语音。

语音输出使用独立的 gemini-3.8-flash-tts，默认 Kore 预设声音，中文灵动活泼。
这是预设合成声音，不是 Alyrra UTAU 音源克隆。TTS_MODEL、TTS_VOICE 在 .env 设置，需重启生效。
对输入语音或 /语音 指令生成语音，成功时只发送语音；生成或 QQ 发送失败时回退到文字。
每次最多朗读回复前 180 字；QQ 上传使用 SILK 格式；每日默认 30 次，独立于积极模式。

```text
@Alyrra /语音 和我打个招呼
@Alyrra /语音模式 自动
@Alyrra /语音模式 始终
@Alyrra /语音模式 关闭
@Alyrra /语音接收 开启
@Alyrra /语音接收 关闭
@Alyrra /语音上限 30
```

除 /语音 外，开关和上限指令需要登记管理员。
实时配置：voice_input_enabled（默认 true），voice_reply_mode（auto/always/off），voice_daily_calls（默认 30）。
voice_usage.json 保存 TTS 日调用计数；失败也计数。用户音频只在临时目录转换，处理后删除。
pilk 提供 SILK 编解码，imageio-ffmpeg 随依赖安装 FFmpeg，无需额外安装系统 FFmpeg。
TTS 模型和 QQ 群富媒体发送权限必须可用。TTS 费用独立于聊天预算，不自动无限重试。

## 预制功能

### 本地卡片

签到和幸运签默认以图片卡片发送，使用 templates/backgrounds 中的固定背景。
晨光歌林、月夜星河、舞台花信三套主题各有两种版式，不产生生图调用。
幸运签只调用一次聊天模型生成签文，排版在本地完成；签到完全本地处理。
渲染或 QQ 上传失败时回退文字，不重复签到或重复请求模型。

管理员可实时设置：/卡片主题 森林、/卡片主题 星河、/卡片主题 舞台、/卡片主题 随机，
以及 /卡片开关 开启、/卡片开关 关闭。
对应实时配置 cards_enabled（默认true）和 card_theme（random/forest/starlight/stage）。
预览在 templates/previews/all_templates.png，运行 cards.py 可重建背景和预览。
非 Windows 系统通过 CARD_FONT 指定中文字体。实际卡片保留在 rendered_cards，最多100张。

```text
@Alyrra /帮助
@Alyrra /签到
@Alyrra /我的资料
@Alyrra /幸运签
@Alyrra /幸运签 工作灵感
@Alyrra /今日运势
@Alyrra /安慰我 今天有点累
@Alyrra /夸夸我
@Alyrra /吐槽我 总是拖延
@Alyrra /总结 30分钟
```

签到和幸运签也支持不带斜杠：发送“签到”“幸运签”或“幸运签 工作灵感”。
原有 /签到、/幸运签 保留，支持 @前缀；普通句子中提及签到不会触发。

签到本地处理，每天一次、获得10歌林星光。称号：0分森林访客、100分练歌伙伴、300分星河听众。
资料、连续签到、功能开关和独立日限额保存于 alyrra.sqlite3，按群隔离，按北京时间换日。

幸运签每次独立调用模型，不复用当天结果；通过随机意象、变化标记和 prompt 保留随机性。
签名、签文、小行动、幸运颜色合计80至150字，定位娱乐创作，不作事实预测。
每人每群每天最多5签；人格互动每人每群每天10次；总结每群每天6次。
所有预制模型功能合计每天60次，积极模式也不能绕过这个独立上限。
这些调用同时计入普通聊天预算；失败模型请求计数，功能已达上限时不调用模型。

群总结仅处理程序实际收到并记录的文字，范围1至120分钟、最多100条和6000字。
不读取加入前消息。图片仅记录标记，语音成功转写后保存转写，不保存原始音频。
数据库在新模块首次运行后开始积累；此前未存储的内存消息不能补回。
记录上限6小时、每群500条，清理在新消息写入时执行；程序停机期间文件不会自动清理。

管理员可发 /功能 幸运签 关闭、/功能 幸运签 开启。
可选功能名为签到、幸运签、人格互动、总结；开关仅影响当前群，关闭功能从 /帮助 中隐藏。
/帮助 和 /功能 在停止模式仍可用，其他预制功能暂停。功能指令直接路由，不额外调用模型判断意图。

测试：.\.venv\Scripts\python.exe -m unittest discover -s tests -v

## 连接问题

### 音色和 RVC 接口

管理员发 /音色 Aoede 或 /音色 Kore 即时更换 TTS 预设音色，保存在实时配置 tts_voice。
有实时设置时它优先于 .env 中的 TTS_VOICE。语音回复成功只发语音，不另外发同内容文字。
回答模型与 TTS 是两种调用：前者生成回答，后者只朗读回答，没有再次调用聊天模型。

RVC 是语音到语音转换，不直接从文字生成声音。预留链路为 TTS WAV → RVC → QQ SILK。
runtime_config.json 中 rvc_enabled 默认 false，尚未配置具体模型或服务。
rvc_command 是命令参数数组，必须包含 {input} 和 {output}，分别替换为临时输入、输出 WAV 路径。
该接口执行本机适配器程序，不使用 shell；超时 120 秒。具体命令需匹配实际 RVC 项目。
模型文件或 API 地址提供后再填写适配器；不要仅有 .pth 文件就直接开启。
RVC 转换失败时回退为文字，避免发送未转换的声音。临时音频完成后删除。

- 启动缺少凭据：重新执行 gcloud auth application-default login。
- QQ 登录失败：检查 AppID、最新 AppSecret 以及沙箱模式。
- 收不到事件：检查 QQ 后台群消息事件权限、服务范围和体验成员设置。
- 收到事件但回复失败：检查 Vertex 权限、网络、配额与 QQ 消息权限。
